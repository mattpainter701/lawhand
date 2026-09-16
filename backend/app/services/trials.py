"""Self-serve trial window helpers.

A trial is a bounded access window on a tenant. Enforcement is deliberately
centralised on ``Tenant.expires_at`` (see
``services/tenant_state.require_active_tenant``) so a lapsed trial fails closed
for every request path, not just the UI. The ``trial`` marker in
``TenantSettings.custom_config`` distinguishes a trial tenant from a paid
tenant that happens to carry an expiry, and gates features that are held back
for the duration of the trial (currently premium AI).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

logger = logging.getLogger(__name__)

TRIAL_MARKER = "trial"
TRIAL_STARTED_KEY = "trial_started_at"
TRIAL_ENDS_KEY = "trial_ends_at"


def trial_period_days() -> int:
    """Return the configured trial length in days, floored at one."""

    settings = get_settings()
    try:
        days = int(getattr(settings, "SIGNUP_TRIAL_DAYS", 30))
    except (TypeError, ValueError):
        days = 30
    return max(1, days)


def new_trial_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the (start, end) instants for a fresh trial window."""

    start = now or datetime.now(timezone.utc)
    return start, start + timedelta(days=trial_period_days())


def trial_config(start: datetime, end: datetime) -> dict[str, Any]:
    """Custom-config fragment marking a tenant as an active trial."""

    return {
        TRIAL_MARKER: True,
        TRIAL_STARTED_KEY: start.isoformat(),
        TRIAL_ENDS_KEY: end.isoformat(),
    }


def config_marks_trial(config: Any) -> bool:
    """True only when the config explicitly carries the trial marker."""

    return bool(isinstance(config, dict) and config.get(TRIAL_MARKER) is True)


async def tenant_on_trial(db: AsyncSession, tenant_id) -> bool:
    """Return whether the tenant is currently flagged as a trial tenant."""

    from app.models.tenant import TenantSettings

    config = await db.scalar(
        select(TenantSettings.custom_config).where(
            TenantSettings.tenant_id == tenant_id
        )
    )
    return config_marks_trial(config)


async def notify_operator_trial_started(
    *,
    tenant_name: str,
    tenant_id,
    admin_email: str,
    trial_ends_at: datetime,
) -> None:
    """Best-effort operator alert when a new trial tenant is provisioned.

    Never raises: a notification failure must not roll back or fail signup.
    """

    from app.services.email import EmailDeliveryResult, email_service

    recipient = (getattr(get_settings(), "MARKETING_LEAD_EMAIL", "") or "").strip()
    if not recipient:
        return

    ends = trial_ends_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"New LawHand trial — {tenant_name}"
    text_body = (
        f"A new firm started a LawHand trial.\n\n"
        f"Firm: {tenant_name}\n"
        f"Admin: {admin_email}\n"
        f"Tenant: {tenant_id}\n"
        f"Trial ends: {ends}\n"
    )
    html_body = (
        "<h2>New LawHand trial</h2>"
        f"<p><strong>Firm:</strong> {tenant_name}<br>"
        f"<strong>Admin:</strong> {admin_email}<br>"
        f"<strong>Tenant:</strong> {tenant_id}<br>"
        f"<strong>Trial ends:</strong> {ends}</p>"
    )
    try:
        delivery = await email_service.send_email(
            [recipient], subject, html_body, text_body
        )
    except Exception:  # pragma: no cover - defensive; send_email already guards
        logger.exception("Trial-start notification raised (tenant_id=%s)", tenant_id)
        return
    if delivery is not EmailDeliveryResult.SENT:
        logger.warning(
            "Trial-start notification not sent (tenant_id=%s, status=%s)",
            tenant_id,
            delivery.value,
        )


async def notify_trial_extended(
    *,
    tenant_name: str,
    recipients: list[str],
    trial_ends_at: datetime,
) -> Any:
    """Tell a firm's administrators that their trial window was extended.

    The operator update is authoritative even when mail is unavailable, so the
    typed delivery result is returned for Platform to surface without rolling
    the extension back.
    """

    from app.services.email import (
        EmailCategory,
        EmailDeliveryResult,
        email_service,
        render_branded_email,
    )

    unique_recipients = sorted(
        {address.strip().lower() for address in recipients if address and "@" in address}
    )
    if not unique_recipients:
        return EmailDeliveryResult.INVALID_RECIPIENT

    end_utc = trial_ends_at.astimezone(timezone.utc)
    end_label = end_utc.strftime("%B %d, %Y at %H:%M UTC")
    safe_name = escape(tenant_name)
    content = f"""
    <div class="header">
      <h1>Your LawHand trial was extended</h1>
      <p>More time for {safe_name} to evaluate the workspace</p>
    </div>
    <div class="body">
      <p>Good news — your LawHand trial has been extended.</p>
      <div class="digest-content">
        <h2 style="margin-top:0;">Your new trial end date</h2>
        <p style="font-size:18px;"><strong>{escape(end_label)}</strong></p>
      </div>
      <p>Your team can continue using its existing workspace and data. Premium
      AI remains governed separately by your account settings.</p>
      <p>If you have questions, reply to your LawHand contact.</p>
    </div>
    """
    text_body = (
        f"Your LawHand trial for {tenant_name} was extended.\n\n"
        f"New trial end date: {end_label}\n\n"
        "Your existing workspace and data remain available."
    )
    return await email_service.send_email(
        unique_recipients,
        "Your LawHand trial has been extended",
        render_branded_email(content),
        text_body,
        category=EmailCategory.NOTIFICATION,
    )
