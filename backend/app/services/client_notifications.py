"""One shape for every notification LawHand sends to a client.

A client is not a user of this product. They get one or two emails a month
from their lawyer's software and have no context to reconstruct what a terse
message means, so each one has to stand on its own:

* the **firm's** name leads, not the platform's -- the client hired a law
  firm, and an unbranded nudge about privileged material reads like phishing;
* it says **what** is waiting and **which matter** it belongs to;
* it says **by when**, where there is a deadline;
* it ends with one obvious action: a link into the client portal.

What it deliberately does not carry is content. Document bodies, message
text and signature pages stay in the portal. An email that reproduced them
would create a second, less protected copy of privileged material in whatever
mailbox the client happens to use.

The link is the plain portal address, which lands on sign-in. Nothing here
carries a session: routine client mail must not be a bearer token, because
inboxes get forwarded, shared and breached long after the notice was read.
``send_client_portal_signin_code`` remains the only way in, and it is sent
only when the client asks for it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.tenant import Tenant, TenantSettings
from app.services.connected_mail import ConnectedMailDelivery, send_client_email
from app.services.email import (
    EmailDeliveryResult,
    cta_button,
    detail_row,
    detail_table,
    email_service,
    labeled_line,
    render_branded_email,
    safe_link,
    text_lines,
)

logger = logging.getLogger(__name__)

# Tabs of the client portal that a notification can send someone straight to.
# Kept in step with TABS in frontend/src/pages/ClientPortalMatterPage.jsx; an
# unknown value would land the client on a page with no tab selected, so
# ``client_portal_url`` refuses anything not listed here.
PORTAL_TABS = frozenset({"overview", "messages", "documents", "signatures", "invoices"})


def client_portal_url(*, tab: str | None = None) -> str:
    """The address of the client portal, optionally opening on one tab.

    One definition, because a link that 404s is worse than no link at all:
    the e-sign invitations pointed at ``/client-portal`` for as long as they
    have existed, and no such route was ever served.
    """
    base = f"{get_settings().FRONTEND_URL.rstrip('/')}/portal/client/matter"
    if tab and tab in PORTAL_TABS:
        return f"{base}?tab={tab}"
    return base


@dataclass(frozen=True)
class FirmIdentity:
    """Who the client thinks they are hearing from."""

    name: str
    phone: str | None = None
    email: str | None = None

    @property
    def display_name(self) -> str:
        return self.name or "Your legal team"


async def firm_identity(db: AsyncSession, tenant_id: str | uuid.UUID) -> FirmIdentity:
    """Resolve the firm's own name and contact details for a tenant.

    Mirrors ``routers.firm.get_firm_branding``'s fallback to the account name,
    but reads it here so a notification service never has to import a router.
    A tenant that cannot be loaded still produces a sendable identity: a
    missing branding row must not cost the client their reminder.
    """
    try:
        tenant_uuid = uuid.UUID(str(tenant_id))
    except (TypeError, ValueError):
        return FirmIdentity(name="Your legal team")
    row = (
        await db.execute(
            select(
                TenantSettings.firm_name,
                TenantSettings.firm_phone,
                TenantSettings.firm_email,
            ).where(TenantSettings.tenant_id == tenant_uuid)
        )
    ).first()
    name = (row.firm_name if row else None) or ""
    if not name.strip():
        name = (
            await db.scalar(select(Tenant.name).where(Tenant.id == tenant_uuid)) or ""
        )
    return FirmIdentity(
        name=name.strip() or "Your legal team",
        phone=(row.firm_phone if row else None) or None,
        email=(row.firm_email if row else None) or None,
    )


def render_client_alert(
    *,
    firm: FirmIdentity,
    headline: str,
    matter_name: str | None = None,
    details: list[tuple[str, str | None]] | None = None,
    deadline_note: str | None = None,
    action_label: str = "Open your client portal",
    action_url: str | None = None,
    recipient_name: str | None = None,
) -> tuple[str, str]:
    """Build the (html, text) bodies of a client notification.

    ``details`` are label/value pairs -- the document, the matter, the date
    something is needed by. They are rendered through the same table as the
    firm's internal alerts so both sides of a matter see the same facts laid
    out the same way.
    """
    url = safe_link(action_url or client_portal_url())
    rows = [detail_row("Matter", matter_name)] if matter_name else []
    rows += [detail_row(label, value) for label, value in (details or [])]
    table = detail_table(rows)

    greeting = f"<p>Hello {escape(recipient_name)},</p>" if recipient_name else ""
    deadline_html = (
        f'<p style="margin-top:16px;"><strong>{escape(deadline_note)}</strong></p>'
        if deadline_note
        else ""
    )
    contact_bits = []
    if firm.phone:
        contact_bits.append(f"call {escape(firm.phone)}")
    if firm.email:
        contact_bits.append(f"email {escape(firm.email)}")
    fallback_html = (
        '<p style="font-size:12px;color:#888;">If the button doesn\'t work, copy '
        f"and paste this link into your browser:<br/>{escape(url)}</p>"
        if url
        else ""
    )
    contact_html = (
        f'<p style="font-size:12px;color:#888;">Questions about this? '
        f"{' or '.join(contact_bits)} to reach {escape(firm.display_name)}.</p>"
        if contact_bits
        else ""
    )

    content = f"""
    <div class="header">
      <h1>{escape(firm.display_name)}</h1>
      <p>{escape(matter_name) if matter_name else "An update on your matter"}</p>
    </div>
    <div class="body">
      {greeting}
      <p>{escape(headline)}</p>
      {table}
      {deadline_html}
      {cta_button(url, action_label)}
      {fallback_html}
      <p style="font-size:12px;color:#888;">You'll be asked to sign in with a
         one-time code sent to this address. Everything to do with your matter
         stays in the portal rather than in email.</p>
      {contact_html}
    </div>
    """

    text = text_lines(
        f"Hello {recipient_name}," if recipient_name else None,
        "",
        headline,
        "",
        labeled_line("Matter", matter_name),
        *[labeled_line(label, value) for label, value in (details or [])],
        deadline_note,
        "",
        f"{action_label}: {url}" if url else None,
        "",
        "You'll be asked to sign in with a one-time code sent to this address.",
        f"Questions? Contact {firm.display_name}."
        + (f" Phone: {firm.phone}." if firm.phone else "")
        + (f" Email: {firm.email}." if firm.email else ""),
    )
    return render_branded_email(content), text


async def send_client_alert(
    db: AsyncSession,
    *,
    tenant_id: str | uuid.UUID,
    actor_user_id: str | uuid.UUID | None,
    to: list[str],
    subject: str,
    headline: str,
    matter_name: str | None = None,
    details: list[tuple[str, str | None]] | None = None,
    deadline_note: str | None = None,
    action_label: str = "Open your client portal",
    action_url: str | None = None,
    recipient_name: str | None = None,
    firm: FirmIdentity | None = None,
) -> ConnectedMailDelivery:
    """Render and send a client notification from the firm's own mailbox.

    Delivery goes through ``send_client_email`` like every other client-facing
    message: the firm's connected mailbox first, then a firm mailbox, then
    platform SMTP, so the client sees a sender they recognize and the firm's
    sent folder records what went out.
    """
    firm = firm or await firm_identity(db, tenant_id)
    html_body, text_body = render_client_alert(
        firm=firm,
        headline=headline,
        matter_name=matter_name,
        details=details,
        deadline_note=deadline_note,
        action_label=action_label,
        action_url=action_url,
        recipient_name=recipient_name,
    )
    subject_prefix = f"{firm.display_name}: " if firm.name else ""
    return await send_client_email(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        to=to,
        subject=f"{subject_prefix}{subject}",
        html_body=html_body,
        text_body=text_body,
        smtp_service=email_service,
    )


__all__ = [
    "EmailDeliveryResult",
    "FirmIdentity",
    "PORTAL_TABS",
    "client_portal_url",
    "firm_identity",
    "render_client_alert",
    "send_client_alert",
]
