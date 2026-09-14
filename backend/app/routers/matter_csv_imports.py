"""Bulk matter creation from the firm's CSV template.

A client who arrives with many live matters is entered once, one row per
matter: the sheet names the matter, the client (reused when a client number,
email or contact ID matches; created otherwise), the attorneys, the open date
and how the engagement stands. Preview resolves every row and reports its
problems; confirm creates the contacts and matters in one transaction.

Nothing here sends anything to a client, fires matter-created automations or
provisions cloud folders: these are historical matters being catalogued, as in
the folder importer. Files and signed fee agreements are added afterwards from
each matter. The run is staged in the external-import tables so a lost
response replays the same result rather than creating the matters twice.
"""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, set_tenant_context
from app.models.contact import Contact
from app.models.external_import import (
    ExternalImportRun,
    ExternalRecordLink,
    ExternalSystemConnection,
)
from app.models.matter_assignment import MatterAssignment
from app.models.plugin import Matter, MatterEvent
from app.models.user import User
from app.routers.matter_imports import INTAKE_STAGES
from app.schemas.matter import MatterCreate
from app.services.access_control import require_capability
from app.services.csv_upload import csv_safe, read_csv_rows
from app.services.matter_engagement import apply_engagement, engagement_event
from app.services.matter_number import assign_matter_number

router = APIRouter(prefix="/api/matter-imports/csv", tags=["matter-imports"])
PROVIDER = "matter_csv_v1"
MAX_BYTES = 1024 * 1024
MAX_ROWS = 500
CLIENT_CONTACT_TYPES = ("client", "prospect")
STATUSES = ("open", "active", "pending")
ENGAGEMENTS = tuple(INTAKE_STAGES)
AGREEMENTS = ("pending_copy", "signed_no_copy", "no_agreement")

# The template's columns, in the order the sheet shows them. Anything else in
# an uploaded file is ignored and reported, never silently mapped.
TEMPLATE_COLUMNS = (
    "matter_name",
    "description",
    "practice_area",
    "matter_type",
    "case_number",
    "court",
    "judge",
    "jurisdiction",
    "venue",
    "role",
    "counterparty",
    "status",
    "opened_on",
    "engagement",
    "agreement",
    "agreement_signed_on",
    "agreement_note",
    "attorney_email",
    "partner_attorney_email",
    "billing_method",
    "hourly_rate",
    "client_id",
    "client_number",
    "client_email",
    "client_first_name",
    "client_last_name",
    "client_organization",
    "client_phone",
)
MATTER_TEXT_COLUMNS = (
    "matter_name",
    "description",
    "practice_area",
    "matter_type",
    "case_number",
    "court",
    "judge",
    "jurisdiction",
    "venue",
    "role",
    "counterparty",
    "billing_method",
)
EXAMPLE_ROW = {
    "matter_name": "Smith v. Acme Corp",
    "description": "Breach of contract transferred from prior counsel",
    "practice_area": "Litigation",
    "matter_type": "Contract Dispute",
    "case_number": "2024-CV-1234",
    "court": "Cook County Circuit Court",
    "judge": "",
    "jurisdiction": "Illinois",
    "venue": "",
    "role": "Plaintiff",
    "counterparty": "Acme Corp",
    "status": "open",
    "opened_on": "2024-02-10",
    "engagement": "existing",
    "agreement": "pending_copy",
    "agreement_signed_on": "2024-02-01",
    "agreement_note": "",
    "attorney_email": "attorney@yourfirm.com",
    "partner_attorney_email": "",
    "billing_method": "hourly",
    "hourly_rate": "350",
    "client_id": "",
    "client_number": "",
    "client_email": "jane.smith@example.com",
    "client_first_name": "Jane",
    "client_last_name": "Smith",
    "client_organization": "",
    "client_phone": "+13125550123",
}


class ConfirmBody(BaseModel):
    confirm: Literal[True]
    # Row numbers (as the preview reported them) to create; omitted means all.
    include_rows: list[int] | None = Field(default=None, max_length=MAX_ROWS)


def _parse_date(value: str, field: str, errors: list[str]) -> date | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field}: use YYYY-MM-DD")
        return None
    if parsed > date.today():
        errors.append(f"{field}: cannot be in the future")
        return None
    if parsed < date(1900, 1, 1):
        errors.append(f"{field}: must be on or after 1900-01-01")
        return None
    return parsed


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def parse_row(row: dict[str, str]) -> tuple[dict, list[str]]:
    """Normalise one CSV row into stored values plus its problems."""
    errors: list[str] = []
    values: dict = {column: row.get(column, "") for column in TEMPLATE_COLUMNS}
    if not values["matter_name"]:
        errors.append("matter_name: required")
    status = (values["status"] or "open").lower()
    if status not in STATUSES:
        errors.append("status: use open, active or pending")
    values["status"] = status
    engagement = (values["engagement"] or "existing").lower()
    if engagement not in ENGAGEMENTS:
        errors.append("engagement: use existing, review or required")
    values["engagement"] = engagement
    agreement = values["agreement"].lower() or None
    if agreement is not None and agreement not in AGREEMENTS:
        errors.append("agreement: use pending_copy, signed_no_copy or no_agreement")
        agreement = None
    signed_on = _parse_date(values["agreement_signed_on"], "agreement_signed_on", errors)
    if engagement == "existing" and agreement is None:
        agreement = "pending_copy"
    if engagement != "existing" and (agreement or signed_on or values["agreement_note"]):
        errors.append("agreement: only an existing engagement records an agreement")
    if agreement in ("signed_no_copy", "no_agreement") and not values["agreement_note"]:
        errors.append(
            "agreement_note: say where it was signed"
            if agreement == "signed_no_copy"
            else "agreement_note: say why there is no fee agreement"
        )
    if agreement == "no_agreement" and signed_on:
        errors.append("agreement_signed_on: a matter with no fee agreement has no signing date")
    values["agreement"] = agreement if engagement == "existing" else None
    values["agreement_signed_on"] = _iso(signed_on)
    opened = _parse_date(values["opened_on"], "opened_on", errors)
    values["opened_on"] = _iso(opened)
    rate = values["hourly_rate"]
    if rate:
        try:
            values["hourly_rate"] = str(Decimal(rate.replace(",", "").lstrip("$")))
        except InvalidOperation:
            errors.append("hourly_rate: use a number")
            values["hourly_rate"] = ""
    values["billing_method"] = (values["billing_method"] or "hourly").lower()
    for field in ("client_email", "attorney_email", "partner_attorney_email"):
        values[field] = values[field].lower()
    if values["client_id"]:
        try:
            uuid.UUID(values["client_id"])
        except ValueError:
            errors.append("client_id: not a contact ID")
            values["client_id"] = ""
    # The matter fields themselves are validated by the same schema the
    # single-matter form uses, so a 600-character name fails the same way.
    try:
        MatterCreate.model_validate(
            {
                **{column: (values[column] or None) for column in MATTER_TEXT_COLUMNS},
                "matter_name": values["matter_name"] or "x",
                "status": status,
                "hourly_rate": values["hourly_rate"] or None,
                "opened_on": opened,
            }
        )
    except ValidationError as exc:
        errors.extend(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in exc.errors()
        )
    return values, errors


def contact_key(values: dict) -> str | None:
    """How rows in one file that name the same new client find each other."""
    if values["client_number"]:
        return f"number:{values['client_number'].casefold()}"
    if values["client_email"]:
        return f"email:{values['client_email']}"
    if values["client_organization"]:
        return f"org:{values['client_organization'].casefold()}"
    if values["client_first_name"] or values["client_last_name"]:
        return f"person:{values['client_first_name'].casefold()}|{values['client_last_name'].casefold()}"
    return None


def display_name(values: dict) -> str:
    person = " ".join(
        part for part in (values["client_first_name"], values["client_last_name"]) if part
    )
    return values["client_organization"] or person or values["client_email"] or values["client_number"]


async def resolve_contacts(db, tenant_id, parsed: list[tuple[dict, list[str]]]):
    """Decide, per row, whether an existing client is reused or one is created."""
    ids = {uuid.UUID(v["client_id"]) for v, _ in parsed if v["client_id"]}
    numbers = {v["client_number"] for v, _ in parsed if v["client_number"]}
    emails = {v["client_email"] for v, _ in parsed if v["client_email"]}
    by_id: dict[uuid.UUID, Contact] = {}
    by_number: dict[str, list[Contact]] = {}
    by_email: dict[str, list[Contact]] = {}
    if ids:
        for contact in (
            await db.scalars(
                select(Contact).where(Contact.tenant_id == tenant_id, Contact.id.in_(ids))
            )
        ).all():
            by_id[contact.id] = contact
    if numbers or emails:
        conditions = []
        if numbers:
            conditions.append(Contact.client_number.in_(numbers))
        if emails:
            conditions.append(func.lower(Contact.email).in_(emails))
        for contact in (
            await db.scalars(
                select(Contact).where(
                    Contact.tenant_id == tenant_id,
                    Contact.contact_type.in_(CLIENT_CONTACT_TYPES),
                    Contact.is_active.is_(True),
                    or_(*conditions),
                )
            )
        ).all():
            if contact.client_number:
                by_number.setdefault(contact.client_number, []).append(contact)
            if contact.email:
                by_email.setdefault(contact.email.lower(), []).append(contact)

    resolutions = []
    for values, errors in parsed:
        resolution: dict = {"action": "create", "contact_id": None, "display_name": display_name(values), "key": None}
        if values["client_id"]:
            contact = by_id.get(uuid.UUID(values["client_id"]))
            if contact is None:
                errors.append("client_id: no such contact in this firm")
            else:
                resolution = {"action": "match", "contact_id": str(contact.id), "display_name": contact.display_name, "key": None}
        else:
            matches = {
                contact.id: contact
                for contact in by_number.get(values["client_number"], [])
                + by_email.get(values["client_email"], [])
            }
            if len(matches) > 1:
                errors.append("client: the client number and email name different contacts; review required")
            elif matches:
                contact = next(iter(matches.values()))
                resolution = {"action": "match", "contact_id": str(contact.id), "display_name": contact.display_name, "key": None}
            else:
                key = contact_key(values)
                if key is None:
                    errors.append("client: give a client number, email, name or organization")
                else:
                    resolution["key"] = key
        resolutions.append(resolution)
    return resolutions


async def resolve_users(db, tenant_id, parsed: list[tuple[dict, list[str]]]):
    emails = {
        v[field]
        for v, _ in parsed
        for field in ("attorney_email", "partner_attorney_email")
        if v[field]
    }
    users = {}
    if emails:
        for user in (
            await db.scalars(
                select(User).where(
                    User.tenant_id == tenant_id,
                    User.is_active.is_(True),
                    func.lower(User.email).in_(emails),
                )
            )
        ).all():
            users[user.email.lower()] = user
    resolved = []
    for values, errors in parsed:
        entry = {}
        for field, key in (("attorney_email", "attorney"), ("partner_attorney_email", "partner")):
            if not values[field]:
                entry[key] = None
                continue
            user = users.get(values[field])
            if user is None:
                errors.append(f"{field}: no active staff member with this email")
                entry[key] = None
            else:
                entry[key] = {"user_id": str(user.id), "name": user.full_name or user.email}
        resolved.append(entry)
    return resolved


def response(run: ExternalImportRun) -> dict:
    manifest = run.manifest or {}
    data = {"id": str(run.id), "status": run.status, "filename": manifest.get("filename")}
    if run.status == "complete":
        data["results"] = manifest.get("results", [])
        data["summary"] = manifest.get("summary", {})
    else:
        data["rows"] = manifest.get("rows", [])
        data["summary"] = manifest.get("summary", {})
        data["ignored_columns"] = manifest.get("ignored_columns", [])
    return data


async def get_run(db, user, run_id, *, lock=False) -> ExternalImportRun:
    await set_tenant_context(db, str(user.tenant_id))
    stmt = select(ExternalImportRun).where(
        ExternalImportRun.id == run_id,
        ExternalImportRun.tenant_id == user.tenant_id,
        ExternalImportRun.provider == PROVIDER,
        ExternalImportRun.created_by_user_id == user.id,
    )
    run = await db.scalar(stmt.with_for_update() if lock else stmt)
    if run is None:
        raise HTTPException(404, "Import not found")
    return run


@router.get("/template")
async def template(user=Depends(require_capability("manage_matters"))):
    """The blank sheet with one example row, hardened against formula cells."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(TEMPLATE_COLUMNS))
    writer.writeheader()
    writer.writerow({column: csv_safe(EXAMPLE_ROW[column]) for column in TEMPLATE_COLUMNS})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="matters-template.csv"'},
    )


@router.post("")
async def preview(
    file: UploadFile = File(...),
    id: uuid.UUID | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_capability("manage_matters")),
):
    """Parse the sheet, resolve every row, and stage the run for confirmation."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "A .csv file is required")
    raw = await file.read(MAX_BYTES + 1)
    try:
        headers, rows = read_csv_rows(
            raw, max_bytes=MAX_BYTES, max_rows=MAX_ROWS, label="matter CSV"
        )
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(413 if "limit" in message else 400, message) from exc
    if "matter_name" not in headers:
        raise HTTPException(400, "The matter CSV needs a matter_name column")
    ignored = sorted(set(headers) - set(TEMPLATE_COLUMNS) - {""})

    parsed = [parse_row(row) for row in rows if row]
    contacts = await resolve_contacts(db, user.tenant_id, parsed)
    staff = await resolve_users(db, user.tenant_id, parsed)
    numbered = [
        {
            "row": number,
            "values": values,
            "contact": contact,
            "attorney": people["attorney"],
            "partner": people["partner"],
            "errors": errors,
        }
        for number, (values, errors), contact, people in zip(
            (index + 2 for index, row in enumerate(rows) if row),
            parsed,
            contacts,
            staff,
        )
    ]
    # Rows that name the same new client are created once, whichever is first.
    seen_keys: set[str] = set()
    for entry in numbered:
        key = entry["contact"].get("key")
        if key and entry["contact"]["action"] == "create":
            if key in seen_keys:
                entry["contact"]["action"] = "create_shared"
            seen_keys.add(key)
    summary = {
        "total": len(numbered),
        "valid": sum(1 for entry in numbered if not entry["errors"]),
        "invalid": sum(1 for entry in numbered if entry["errors"]),
        "contacts_matched": sum(1 for entry in numbered if entry["contact"]["action"] == "match"),
        "contacts_to_create": len(seen_keys),
    }
    manifest = {
        "filename": (file.filename or "")[:255],
        "sha256": hashlib.sha256(raw).hexdigest(),
        "ignored_columns": ignored,
        "rows": numbered,
        "summary": summary,
    }

    run_id = id or uuid.uuid4()
    await set_tenant_context(db, str(user.tenant_id))
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"{user.tenant_id}:matter-csv:{run_id}"},
    )
    existing = await db.scalar(
        select(ExternalImportRun).where(ExternalImportRun.id == run_id)
    )
    if existing is not None:
        if (
            existing.tenant_id != user.tenant_id
            or existing.created_by_user_id != user.id
            or existing.provider != PROVIDER
        ):
            raise HTTPException(409, "Import identifier unavailable")
        if existing.manifest.get("sha256") != manifest["sha256"]:
            raise HTTPException(409, "A different file was previewed under this import. Start a new import.")
        return response(existing)
    connection = ExternalSystemConnection(
        id=run_id,
        tenant_id=user.tenant_id,
        provider=PROVIDER,
        external_key=str(run_id),
        display_name="Matter CSV upload",
        created_by_user_id=user.id,
    )
    db.add(connection)
    await db.flush()
    run = ExternalImportRun(
        id=run_id,
        tenant_id=user.tenant_id,
        connection_id=connection.id,
        provider=PROVIDER,
        created_by_user_id=user.id,
        status="review",
        manifest=manifest,
        row_counts={"rows": len(numbered)},
    )
    db.add(run)
    await db.commit()
    return response(run)


@router.get("/{run_id}")
async def status(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_capability("manage_matters")),
):
    return response(await get_run(db, user, run_id))


@router.post("/{run_id}/confirm")
async def confirm(
    run_id: uuid.UUID,
    body: ConfirmBody,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_capability("manage_matters")),
):
    """Create the reviewed rows' contacts and matters in one transaction."""
    run = await get_run(db, user, run_id, lock=True)
    if run.status == "complete":
        return response(run)
    if run.status != "review":
        raise HTTPException(409, "This import is not awaiting confirmation")
    rows = run.manifest.get("rows", [])
    wanted = set(body.include_rows) if body.include_rows is not None else None
    included = [entry for entry in rows if wanted is None or entry["row"] in wanted]
    if not included:
        raise HTTPException(422, "Include at least one row")
    problems = [entry["row"] for entry in included if entry["errors"]]
    if problems:
        raise HTTPException(
            422,
            "Fix or exclude the rows with problems before creating matters: "
            + ", ".join(str(number) for number in problems[:20]),
        )

    tenant_id = user.tenant_id
    now = datetime.now(timezone.utc)
    # Matched contacts and staff must still exist; a preview can go stale.
    matched_ids = {
        uuid.UUID(entry["contact"]["contact_id"])
        for entry in included
        if entry["contact"]["contact_id"]
    }
    live_contacts = set()
    if matched_ids:
        live_contacts = set(
            (
                await db.scalars(
                    select(Contact.id).where(
                        Contact.tenant_id == tenant_id, Contact.id.in_(matched_ids)
                    )
                )
            ).all()
        )
    user_ids = {
        uuid.UUID(entry[key]["user_id"])
        for entry in included
        for key in ("attorney", "partner")
        if entry.get(key)
    }
    live_users = set()
    if user_ids:
        live_users = set(
            (
                await db.scalars(
                    select(User.id).where(
                        User.tenant_id == tenant_id,
                        User.is_active.is_(True),
                        User.id.in_(user_ids),
                    )
                )
            ).all()
        )
    stale = [
        entry["row"]
        for entry in included
        if (
            entry["contact"]["contact_id"]
            and uuid.UUID(entry["contact"]["contact_id"]) not in live_contacts
        )
        or any(
            entry.get(key) and uuid.UUID(entry[key]["user_id"]) not in live_users
            for key in ("attorney", "partner")
        )
    ]
    if stale:
        raise HTTPException(
            409,
            "A client or staff member named in the preview no longer exists; preview the file again. Rows: "
            + ", ".join(str(number) for number in stale[:20]),
        )

    created_contacts: dict[str, Contact] = {}
    results = []
    for entry in included:
        values = entry["values"]
        contact_info = entry["contact"]
        contact_created = False
        if contact_info["contact_id"]:
            contact_id = uuid.UUID(contact_info["contact_id"])
        else:
            key = contact_info["key"]
            contact = created_contacts.get(key)
            if contact is None:
                contact = Contact(
                    id=uuid.uuid5(run.id, f"contact:{key}"),
                    tenant_id=tenant_id,
                    entity_type="organization" if values["client_organization"] else "person",
                    contact_type="client",
                    client_status="active",
                    first_name=values["client_first_name"] or None,
                    last_name=values["client_last_name"] or None,
                    organization_name=values["client_organization"] or None,
                    email=values["client_email"] or None,
                    phone=values["client_phone"] or None,
                    client_number=values["client_number"] or None,
                    created_by_user_id=user.id,
                )
                db.add(contact)
                await db.flush()
                created_contacts[key] = contact
                db.add(
                    ExternalRecordLink(
                        tenant_id=tenant_id,
                        provider=PROVIDER,
                        source_table="contacts",
                        source_row_key=f"{run.id}:{key}",
                        import_run_id=run.id,
                        target_table="contacts",
                        target_record_id=contact.id,
                        confidence="exact",
                    )
                )
                contact_created = True
            contact_id = contact.id

        opened_on = (
            date.fromisoformat(values["opened_on"]) if values["opened_on"] else now.date()
        )
        attorney_id = uuid.UUID(entry["attorney"]["user_id"]) if entry.get("attorney") else None
        partner_id = uuid.UUID(entry["partner"]["user_id"]) if entry.get("partner") else None
        matter_id = uuid.uuid5(run.id, f"row:{entry['row']}")
        matter = Matter(
            id=matter_id,
            tenant_id=tenant_id,
            user_id=user.id,
            slug=f"import-{matter_id.hex}",
            matter_name=values["matter_name"],
            description=values["description"] or None,
            practice_area=values["practice_area"] or None,
            matter_type=values["matter_type"] or "general",
            case_number=values["case_number"] or None,
            court=values["court"] or None,
            judge=values["judge"] or None,
            jurisdiction=values["jurisdiction"] or None,
            venue=values["venue"] or None,
            role=values["role"] or None,
            counterparty=values["counterparty"] or None,
            status=values["status"],
            stage=INTAKE_STAGES[values["engagement"]],
            source="csv_import",
            opened_on=opened_on,
            retention_until=opened_on + timedelta(days=365 * 7),
            billing_method=values["billing_method"] or "hourly",
            hourly_rate=Decimal(values["hourly_rate"]) if values["hourly_rate"] else None,
            client_contact_id=contact_id,
            attorney_of_record_id=attorney_id,
            partner_attorney_id=partner_id,
        )
        if values["agreement"]:
            apply_engagement(
                matter,
                status=values["agreement"],
                signed_on=(
                    date.fromisoformat(values["agreement_signed_on"])
                    if values["agreement_signed_on"]
                    else None
                ),
                note=values["agreement_note"],
                document_id=None,
                user_id=user.id,
                at=now,
            )
        await assign_matter_number(db, matter)
        db.add(matter)
        await db.flush()
        # The attorney of record leads; the person running the import is on
        # the matter too, as create_matter would have it.
        assignees = {user.id}
        if attorney_id:
            assignees.add(attorney_id)
        primary = attorney_id or user.id
        for assignee in assignees:
            db.add(
                MatterAssignment(
                    tenant_id=tenant_id,
                    matter_id=matter.id,
                    user_id=assignee,
                    role="lead_attorney" if assignee == primary else "associate",
                    is_primary=assignee == primary,
                )
            )
        db.add(
            MatterEvent(
                tenant_id=tenant_id,
                matter_id=matter.id,
                event_type="intake",
                title="Existing matter imported",
                content=(
                    f"CSV import {run.id}, row {entry['row']}; engagement: "
                    f"{values['engagement']}; opened {opened_on.isoformat()}. No messages sent."
                ),
                note_type="system",
                created_by=user.id,
            )
        )
        if values["agreement"]:
            engagement_event(
                db,
                matter,
                user_id=user.id,
                actor=getattr(user, "full_name", None) or getattr(user, "email", None) or str(user.id),
                extra=f"From CSV import row {entry['row']}.",
            )
        db.add(
            ExternalRecordLink(
                tenant_id=tenant_id,
                provider=PROVIDER,
                source_table="rows",
                source_row_key=f"{run.id}:{entry['row']}",
                import_run_id=run.id,
                target_table="matters",
                target_record_id=matter.id,
                confidence="exact",
            )
        )
        results.append(
            {
                "row": entry["row"],
                "matter_id": str(matter.id),
                "matter_number": matter.matter_number,
                "matter_name": matter.matter_name,
                "contact_id": str(contact_id),
                "contact_created": contact_created,
            }
        )

    run.status = "complete"
    run.promoted_at = now
    run.manifest = {
        **run.manifest,
        "confirmed_rows": sorted(wanted) if wanted is not None else None,
        "results": results,
        "summary": {
            **run.manifest.get("summary", {}),
            "created_matters": len(results),
            "created_contacts": len(created_contacts),
        },
    }
    await db.commit()
    return response(run)
