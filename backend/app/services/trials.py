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
SIGNUP_STATUS_KEY = "signup_status"
SIGNUP_PENDING = "pending"
SIGNUP_APPROVED = "approved"


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


async def notify_operator_signup_requested(
    *, tenant_name: str, tenant_id, admin_email: str, requested_plan: str
) -> None:
    """Best-effort alert for a registration that still needs approval."""

    from app.services.email import email_service

    recipient = (getattr(get_settings(), "MARKETING_LEAD_EMAIL", "") or "").strip()
    if not recipient:
        return
    safe_name = escape(tenant_name)
    safe_email = escape(admin_email)
    html_body = (
        "<h2>New LawHand registration awaiting approval</h2>"
        f"<p><strong>Firm:</strong> {safe_name}<br>"
        f"<strong>Admin:</strong> {safe_email}<br>"
        f"<strong>Requested plan:</strong> {escape(requested_plan)}<br>"
        f"<strong>Tenant:</strong> {tenant_id}</p>"
        "<p>No workspace access or trial spend has started.</p>"
    )
    text_body = (
        "A new LawHand registration is awaiting Platform approval.\n\n"
        f"Firm: {tenant_name}\nAdmin: {admin_email}\n"
        f"Requested plan: {requested_plan}\nTenant: {tenant_id}\n\n"
        "No workspace access or trial spend has started."
    )
    try:
        await email_service.send_email(
            [recipient],
            f"LawHand registration awaiting approval — {tenant_name}",
            html_body,
            text_body,
        )
    except Exception:  # pragma: no cover - best effort by design
        logger.exception("Signup-request notification raised (tenant_id=%s)", tenant_id)


async def notify_trial_approved(
    *,
    tenant_name: str,
    recipients: list[str],
    trial_ends_at: datetime,
    premium_ai_enabled: bool,
) -> Any:
    """Tell approved founders that their previously registered login is live."""

    from app.services.email import EmailCategory, email_service, render_branded_email

    unique_recipients = sorted(
        {
            address.strip().lower()
            for address in recipients
            if address and "@" in address
        }
    )
    if not unique_recipients:
        from app.services.email import EmailDeliveryResult

        return EmailDeliveryResult.INVALID_RECIPIENT
    end_label = trial_ends_at.astimezone(timezone.utc).strftime("%B %d, %Y")
    login_url = (get_settings().FRONTEND_URL or "http://localhost:3000").rstrip("/")
    safe_login_url = escape(f"{login_url}/login", quote=True)
    premium_label = "enabled for this sponsored trial" if premium_ai_enabled else "off"
    content = f"""
    <div class="header">
      <h1>Your LawHand trial is approved</h1>
      <p>{escape(tenant_name)} can now enter its workspace</p>
    </div>
    <div class="body">
      <p>Your registration has been approved. Sign in with the email and
      password you chose when you registered.</p>
      <p style="margin:28px 0;">
        <a href="{safe_login_url}" style="background:#14253B;color:#fff;padding:13px 24px;border-radius:7px;text-decoration:none;font-weight:600;">Sign in to LawHand</a>
      </p>
      <div class="digest-content">
        <p><strong>Trial access through:</strong> {escape(end_label)}</p>
        <p><strong>Premium AI:</strong> {escape(premium_label)}</p>
      </div>
    </div>
    """
    text_body = (
        f"Your LawHand trial for {tenant_name} is approved.\n\n"
        f"Sign in: {login_url}/login\n"
        f"Trial access through: {end_label}\n"
        f"Premium AI: {premium_label}\n"
    )
    return await email_service.send_email(
        unique_recipients,
        "Your LawHand trial is approved",
        render_branded_email(content),
        text_body,
        category=EmailCategory.SECURITY,
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
        {
            address.strip().lower()
            for address in recipients
            if address and "@" in address
        }
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


async def notify_trial_invited(
    *,
    tenant_name: str,
    admin_email: str,
    admin_name: str | None,
    invitation_url: str,
    trial_ends_at: datetime,
) -> Any:
    """Invite a founding administrator into an operator-created trial.

    The firm and its hashed invitation already exist when this runs. Delivery
    is therefore reported to Platform instead of rolling provisioning back;
    the one-time response also carries the acceptance URL for manual recovery.
    """

    from app.services.email import (
        EmailCategory,
        email_service,
        render_branded_email,
    )

    end_label = trial_ends_at.astimezone(timezone.utc).strftime("%B %d, %Y")
    safe_firm = escape(tenant_name)
    safe_name = escape(admin_name or "there")
    safe_url = escape(invitation_url, quote=True)
    content = f"""
    <div class="header">
      <h1>Your LawHand workspace is ready</h1>
      <p>{safe_firm} has been invited to a private trial</p>
    </div>
    <div class="body">
      <p>Hi {safe_name},</p>
      <p>Your LawHand workspace has been created. Set your password and enter
      the workspace using the secure invitation below.</p>
      <p style="margin:28px 0;">
        <a href="{safe_url}" style="background:#14253B;color:#fff;padding:13px 24px;border-radius:7px;text-decoration:none;font-weight:600;">
          Set up my LawHand account
        </a>
      </p>
      <div class="digest-content">
        <h2 style="margin-top:0;">Trial details</h2>
        <p><strong>Trial access through:</strong> {escape(end_label)}</p>
        <p>Premium AI is controlled separately by your LawHand contact.</p>
      </div>
      <p style="color:#666;font-size:13px;">For security, this invitation link
      expires in 7 days. If it expires, ask your LawHand contact for a new one.</p>
    </div>
    """
    text_body = (
        f"Hi {admin_name or 'there'},\n\n"
        f"Your LawHand workspace for {tenant_name} is ready.\n"
        f"Set up your account: {invitation_url}\n\n"
        f"Trial access through: {end_label}\n"
        "This secure invitation expires in 7 days."
    )
    return await email_service.send_email(
        [admin_email],
        "Your LawHand workspace is ready",
        render_branded_email(content),
        text_body,
        category=EmailCategory.SECURITY,
    )
