"""Operator alert for a support request a tenant administrator has filed."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape

from app.config import get_settings

logger = logging.getLogger(__name__)


async def notify_operator_support_requested(
    *,
    tenant_name: str,
    tenant_id,
    request_id,
    severity: str,
    subject: str,
    safe_summary: str,
    requested_by_email: str,
    acknowledgement_due_at: datetime,
) -> None:
    """Best-effort alert so a new request reaches a person, not only a queue.

    The acknowledgement clock starts when the request is filed — continuously
    for S1 — so waiting for someone to open the operator console can spend the
    whole objective. Uses the same operator inbox as the registration alerts.
    Never raises: an alert failure must not fail the customer's request.
    """

    from app.services.email import email_service

    recipient = (getattr(get_settings(), "MARKETING_LEAD_EMAIL", "") or "").strip()
    if not recipient:
        return

    due = acknowledgement_due_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text_body = (
        f"A tenant administrator filed a {severity} support request.\n\n"
        f"Firm: {tenant_name}\n"
        f"Requested by: {requested_by_email}\n"
        f"Subject: {subject}\n"
        f"Acknowledge by: {due}\n"
        f"Tenant: {tenant_id}\n"
        f"Request: {request_id}\n\n"
        f"{safe_summary}\n\n"
        "Acknowledge it from the operator console Support tab."
    )
    html_body = (
        f"<h2>{escape(severity)} support request</h2>"
        f"<p><strong>Firm:</strong> {escape(tenant_name)}<br>"
        f"<strong>Requested by:</strong> {escape(requested_by_email)}<br>"
        f"<strong>Subject:</strong> {escape(subject)}<br>"
        f"<strong>Acknowledge by:</strong> {due}<br>"
        f"<strong>Tenant:</strong> {tenant_id}<br>"
        f"<strong>Request:</strong> {request_id}</p>"
        f"<p>{escape(safe_summary)}</p>"
        "<p>Acknowledge it from the operator console Support tab.</p>"
    )
    try:
        await email_service.send_email(
            [recipient],
            f"[{severity}] LawHand support request — {tenant_name}",
            html_body,
            text_body,
        )
    except Exception:
        logger.exception(
            "Support-request notification raised (tenant_id=%s request_id=%s)",
            tenant_id,
            request_id,
        )
