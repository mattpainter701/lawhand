"""Explicit calendar schedules using the same reviewed draft path as manual billing."""

import calendar
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select

from app.database import set_tenant_context
from app.models.billing import BillingSchedule
from app.models.plugin import Matter
from app.models.user import User
from app.schemas.billing import GenerateInvoiceRequest


def next_calendar_date(current: date, months: int, anchor_day: int) -> date:
    month_index = current.year * 12 + current.month - 1 + months
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))


async def run_schedules(db, tenant_id):
    from app.routers.billing_extended import _generate_invoice
    from app.services.access_control import can_manage_finance
    from app.services.rbac_service import get_user_capabilities

    await set_tenant_context(db, str(tenant_id))
    ids = (
        (
            await db.execute(
                select(BillingSchedule.id).where(
                    BillingSchedule.tenant_id == tenant_id,
                    BillingSchedule.paused.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    for schedule_id in ids:
        # Re-read after every commit; never reuse expired schedule/user objects.
        for _ in range(12):
            await set_tenant_context(db, str(tenant_id))
            schedule = await db.scalar(
                select(BillingSchedule)
                .where(
                    BillingSchedule.id == schedule_id,
                    BillingSchedule.tenant_id == tenant_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not schedule or schedule.paused:
                await db.rollback()
                break
            config = schedule.config
            today = (
                datetime.now(timezone.utc)
                .astimezone(ZoneInfo(config["timezone"]))
                .date()
            )
            due = schedule.next_date
            end = (
                date.fromisoformat(config["end_date"])
                if config.get("end_date")
                else None
            )
            if due > today or (end and due > end):
                await db.rollback()
                break
            matter = await db.scalar(
                select(Matter)
                .where(Matter.id == schedule.matter_id, Matter.tenant_id == tenant_id)
                .execution_options(populate_existing=True)
            )
            user = await db.scalar(
                select(User)
                .where(User.id == schedule.created_by, User.tenant_id == tenant_id)
                .execution_options(populate_existing=True)
            )
            capabilities = (
                await get_user_capabilities(db, user.id)
                if user and user.is_active
                else set()
            )
            if (
                not matter
                or matter.is_closed
                or matter.billing_method == "pro_bono"
                or not user
                or not user.is_active
                or not (
                    can_manage_finance(user.role) or "manage_billing" in capabilities
                )
            ):
                schedule.paused = True
                schedule.last_error = (
                    "Schedule paused: review matter status and billing owner access."
                )
                await db.commit()
                break
            charges = []
            if config["fixed_amount"] != "0":
                from decimal import Decimal

                if Decimal(config["fixed_amount"]) > 0:
                    charges = [
                        {
                            "description": f"{config['fixed_description']} (period ending {due - timedelta(days=1)})",
                            "unit_price": config["fixed_amount"],
                        }
                    ]
            body = GenerateInvoiceRequest(
                matter_id=str(schedule.matter_id),
                issue_date=due,
                date_to=due - timedelta(days=1),
                manual_charges=charges,
                time_entry_ids=None if config["include_unbilled_work"] else [],
                expense_ids=None if config["include_unbilled_work"] else [],
                generation_key=uuid.uuid5(schedule_id, due.isoformat()),
            )
            following = next_calendar_date(
                due, config["interval_months"], config["anchor_day"]
            )
            try:
                # The generator commits the draft AND the next date together.
                schedule.next_date = following
                schedule.last_error = None
                await _generate_invoice(body, user, db)
            except HTTPException as exc:
                await db.rollback()
                await set_tenant_context(db, str(tenant_id))
                schedule = await db.scalar(
                    select(BillingSchedule)
                    .where(BillingSchedule.id == schedule_id)
                    .with_for_update()
                )
                if not schedule or schedule.paused or schedule.next_date != due:
                    await db.rollback()
                    break
                if (
                    exc.status_code == 400
                    and exc.detail
                    == "No unbilled time entries or expenses found for this matter"
                ):
                    schedule.next_date = following
                    await db.commit()
                    continue
                schedule.last_error = (
                    "Draft could not be prepared. Review billing and retry."
                )
                await db.commit()
                break
            except Exception:
                await db.rollback()
                await set_tenant_context(db, str(tenant_id))
                schedule = await db.scalar(
                    select(BillingSchedule)
                    .where(BillingSchedule.id == schedule_id)
                    .with_for_update()
                )
                if not schedule or schedule.paused or schedule.next_date != due:
                    await db.rollback()
                    break
                schedule.last_error = (
                    "Draft preparation failed. Review billing before retrying."
                )
                await db.commit()
                break
