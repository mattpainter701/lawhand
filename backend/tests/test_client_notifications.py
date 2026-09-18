"""The shape of every notification LawHand sends to a client."""

import uuid
from types import SimpleNamespace

import pytest

from app.models.tenant import TenantSettings
from app.services import client_notifications
from app.services.client_notifications import (
    FirmIdentity,
    client_portal_url,
    firm_identity,
    render_client_alert,
)


def test_portal_url_points_at_a_route_that_exists():
    """The e-sign mails pointed at /client-portal, which was never a route."""
    url = client_portal_url()
    assert url.endswith("/portal/client/matter")
    assert client_portal_url(tab="signatures").endswith(
        "/portal/client/matter?tab=signatures"
    )


def test_portal_url_ignores_a_tab_the_portal_does_not_have():
    assert client_portal_url(tab="not-a-tab").endswith("/portal/client/matter")


def test_client_alert_leads_with_the_firm_and_says_what_is_needed():
    firm = FirmIdentity(name="Painter Law", phone="701-555-0100", email="hi@pl.example")
    html, text = render_client_alert(
        firm=firm,
        headline="Engagement Letter.pdf is still waiting for your signature.",
        matter_name="Doe Estate Administration",
        recipient_name="Jane Doe",
        details=[("Document", "Engagement Letter.pdf"), ("Sign by", "October 01, 2026")],
        deadline_note="Please sign by October 01, 2026 — 13 days from now.",
        action_label="Review and sign in your portal",
        action_url=client_portal_url(tab="signatures"),
    )

    # The firm the client hired leads, not the platform they have never heard of.
    assert "Painter Law" in html
    assert html.index("Painter Law") < html.index("Doe Estate Administration")
    assert "Hello Jane Doe," in html
    assert "Engagement Letter.pdf" in html
    assert "October 01, 2026" in html
    assert "13 days from now" in html
    assert "Review and sign in your portal" in html
    assert "/portal/client/matter?tab=signatures" in html
    # A client deciding whether to click a link to privileged material can see
    # where it goes, in both parts.
    assert "/portal/client/matter?tab=signatures" in text
    assert "one-time code" in text
    assert "701-555-0100" in text


def test_client_alert_escapes_every_interpolated_value():
    html, _text = render_client_alert(
        firm=FirmIdentity(name="Painter <Law>"),
        headline="A document is ready.<script>alert(1)</script>",
        matter_name="Doe & Sons",
        details=[("Document", "<b>evil</b>.pdf")],
    )
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Painter &lt;Law&gt;" in html
    assert "Doe &amp; Sons" in html
    assert "&lt;b&gt;evil&lt;/b&gt;.pdf" in html


def test_client_alert_never_carries_a_session_bearing_link():
    """Routine client mail must not be a bearer token for privileged material."""
    html, text = render_client_alert(
        firm=FirmIdentity(name="Painter Law"),
        headline="Something is waiting for you.",
    )
    for body in (html, text):
        assert "token=" not in body
        assert "?t=" not in body
        assert "one-time code" in body or "one-time code" in text


def test_client_alert_falls_back_when_the_firm_has_no_name():
    html, text = render_client_alert(
        firm=FirmIdentity(name=""),
        headline="Something is waiting for you.",
    )
    assert "Your legal team" in html
    assert "Your legal team" in text


@pytest.mark.asyncio
async def test_firm_identity_prefers_branding_then_the_account_name(
    db_session, test_tenant
):
    resolved = await firm_identity(db_session, test_tenant.id)
    assert resolved.name == test_tenant.name

    db_session.add(
        TenantSettings(
            tenant_id=test_tenant.id,
            firm_name="Painter Law",
            firm_phone="701-555-0100",
        )
    )
    await db_session.commit()

    resolved = await firm_identity(db_session, test_tenant.id)
    assert resolved.name == "Painter Law"
    assert resolved.phone == "701-555-0100"


@pytest.mark.asyncio
async def test_firm_identity_survives_a_tenant_it_cannot_resolve(db_session):
    """A missing branding row must never cost a client their notification."""
    resolved = await firm_identity(db_session, "not-a-uuid")
    assert resolved.display_name == "Your legal team"
    resolved = await firm_identity(db_session, uuid.uuid4())
    assert resolved.display_name == "Your legal team"


@pytest.mark.asyncio
async def test_send_client_alert_goes_out_as_the_firm(monkeypatch):
    sent = {}

    async def fake_send_client_email(db, **kwargs):
        sent.update(kwargs)
        return SimpleNamespace(result="sent")

    monkeypatch.setattr(
        client_notifications, "send_client_email", fake_send_client_email
    )
    await client_notifications.send_client_alert(
        None,
        tenant_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        to=["client@example.com"],
        subject="A new document is available",
        headline="Your legal team shared a document with you.",
        matter_name="Doe Estate Administration",
        firm=FirmIdentity(name="Painter Law"),
    )

    assert sent["subject"] == "Painter Law: A new document is available"
    assert sent["to"] == ["client@example.com"]
    assert "Doe Estate Administration" in sent["html_body"]
    assert "Doe Estate Administration" in sent["text_body"]
