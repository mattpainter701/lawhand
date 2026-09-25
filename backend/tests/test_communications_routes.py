"""Communications list/detail/edit: readable names, locked evidence, safe re-filing."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt as jose_jwt

from app.config import get_settings
from app.models.communication_log import CommunicationLog
from app.models.contact import Contact
from app.models.plugin import Matter
from app.models.user import User

settings = get_settings()


async def _matter(db_session, tenant, owner, name, number=None):
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=owner.id,
        slug=f"m-{uuid.uuid4().hex[:8]}",
        matter_name=name,
        matter_number=number,
    )
    db_session.add(matter)
    await db_session.commit()
    return matter.id


async def _log(db_session, tenant, **fields):
    row = CommunicationLog(
        tenant_id=tenant.id,
        direction=fields.pop("direction", "inbound"),
        channel=fields.pop("channel", "email"),
        status=fields.pop("status", "logged"),
        subject=fields.pop("subject", "Subject"),
        **fields,
    )
    db_session.add(row)
    await db_session.commit()
    return row.id


@pytest.mark.asyncio
async def test_list_and_detail_show_matter_and_contact_names(
    client, db_session, test_tenant, test_user
):
    matter_id = await _matter(
        db_session, test_tenant, test_user, "Smith Divorce", "M-0042"
    )
    contact = Contact(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        first_name="Jane",
        last_name="Smith",
        email="jane@smith.example",
    )
    db_session.add(contact)
    await db_session.commit()
    contact_id = contact.id
    log_id = await _log(
        db_session,
        test_tenant,
        matter_id=matter_id,
        contact_id=contact_id,
        subject="Captured",
        status="received",
        external_ref="google:abc",
    )

    listing = await client.get("/api/communications")
    assert listing.status_code == 200
    item = next(i for i in listing.json()["items"] if i["id"] == str(log_id))
    assert item["matter_name"] == "Smith Divorce"
    assert item["matter_number"] == "M-0042"
    assert item["contact_name"] == "Jane Smith"
    assert item["content_locked"] is True

    detail = await client.get(f"/api/communications/{log_id}")
    assert detail.status_code == 200
    assert detail.json()["matter_name"] == "Smith Divorce"

    history = await client.get(f"/api/contacts/{contact_id}/communications")
    assert history.status_code == 200
    assert history.json()["items"][0]["matter_name"] == "Smith Divorce"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"status": "received", "external_ref": "google:captured"},
        {"status": "sent"},
        {"channel": "portal"},
        {"external_ref": "task:1:contacted"},
    ],
)
async def test_captured_record_content_cannot_be_rewritten(
    client, db_session, test_tenant, fields
):
    log_id = await _log(db_session, test_tenant, subject="What was said", **fields)

    response = await client.patch(
        f"/api/communications/{log_id}", json={"subject": "Something else"}
    )
    assert response.status_code == 409
    assert "cannot be edited" in response.json()["detail"]
    detail = await client.get(f"/api/communications/{log_id}")
    assert detail.json()["subject"] == "What was said"


@pytest.mark.asyncio
async def test_unchanged_content_does_not_block_refiling_a_captured_record(
    client, db_session, test_tenant, test_user
):
    target = await _matter(db_session, test_tenant, test_user, "Right matter")
    log_id = await _log(
        db_session,
        test_tenant,
        subject="Captured",
        status="received",
        external_ref="google:refile",
    )

    # The old edit form sent every field back; resending the same subject
    # alongside the new matter must still be accepted as a pure re-file.
    response = await client.patch(
        f"/api/communications/{log_id}",
        json={"subject": "Captured", "matter_id": str(target)},
    )
    assert response.status_code == 200
    assert response.json()["matter_id"] == str(target)
    assert response.json()["matter_name"] == "Right matter"


@pytest.mark.asyncio
async def test_hand_logged_entry_stays_editable(client, db_session, test_tenant):
    log_id = await _log(db_session, test_tenant, subject="Call with client")

    response = await client.patch(
        f"/api/communications/{log_id}", json={"summary": "Discussed hearing"}
    )
    assert response.status_code == 200
    assert response.json()["summary"] == "Discussed hearing"
    assert response.json()["content_locked"] is False


@pytest.mark.asyncio
async def test_refiling_requires_access_to_the_target_matter(
    client, db_session, test_tenant, test_user
):
    staff = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email=f"para-{uuid.uuid4().hex[:6]}@testfirm.com",
        full_name="Paralegal",
        role="paralegal",
        oauth_provider="google",
        oauth_subject=f"google-{uuid.uuid4().hex}",
        is_active=True,
    )
    db_session.add(staff)
    await db_session.commit()
    staff_id = staff.id
    own = await _matter(db_session, test_tenant, staff, "Staff matter")
    other = await _matter(db_session, test_tenant, test_user, "Restricted matter")
    log_id = await _log(db_session, test_tenant, matter_id=own)
    token = jose_jwt.encode(
        {
            "sub": str(staff_id),
            "tenant_id": str(test_tenant.id),
            "role": "paralegal",
            "email": "para@testfirm.com",
            "billing_tier": test_tenant.billing_tier,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = await client.patch(
        f"/api/communications/{log_id}",
        json={"matter_id": str(other)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Matter not found"


@pytest.mark.asyncio
async def test_refiling_to_an_unknown_contact_is_refused(
    client, db_session, test_tenant
):
    log_id = await _log(db_session, test_tenant)

    response = await client.patch(
        f"/api/communications/{log_id}", json={"contact_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Contact not found"


@pytest.mark.asyncio
async def test_deleted_entries_leave_contact_history_and_matter_correspondence(
    client, db_session, test_tenant, test_user
):
    matter_id = await _matter(db_session, test_tenant, test_user, "History matter")
    contact = Contact(id=uuid.uuid4(), tenant_id=test_tenant.id, first_name="Ann")
    db_session.add(contact)
    await db_session.commit()
    contact_id = contact.id
    await _log(
        db_session,
        test_tenant,
        matter_id=matter_id,
        contact_id=contact_id,
        status="deleted",
        subject="Removed",
    )

    history = await client.get(f"/api/contacts/{contact_id}/communications")
    assert history.json()["total"] == 0
    correspondence = await client.get(f"/api/matters/{matter_id}/correspondence")
    assert correspondence.json()["total"] == 0
