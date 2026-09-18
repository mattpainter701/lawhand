"""The estate inventory overlay in the native client portal fails closed."""

import hashlib
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.client_portal import ClientPortalInvite
from app.models.contact import Contact
from app.models.estate import EstateAsset
from app.models.plugin import Estate, EstateEvent, Matter, TenantPluginEntitlement
from app.routers.client_portal import CLIENT_PORTAL_COOKIE_NAME
from app.services.portal_token import create_matter_portal_token

PORTAL = "/api/portal/client"
STAFF = "/api/plugins/trust-estate"


@pytest_asyncio.fixture
async def estate_portal(db_session, test_tenant, test_user):
    from app.models.rbac import Role, UserRole

    staff_role = Role(
        tenant_id=test_tenant.id,
        name="Estate staff",
        capabilities=["manage_matters"],
    )
    db_session.add(staff_role)
    await db_session.flush()
    db_session.add(
        UserRole(
            user_id=test_user.id,
            role_id=staff_role.id,
            tenant_id=test_tenant.id,
            source="manual",
        )
    )
    contact = Contact(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        contact_type="client",
        client_status="active",
        first_name="Ann",
        last_name="Olson",
        email="ann@example.com",
    )
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"probate-portal-{uuid.uuid4().hex[:8]}",
        matter_name="Estate of Ole Olson",
        matter_type="probate",
        status="open",
        portal_enabled=True,
        client_contact_id=contact.id,
    )
    estate = Estate(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        title="Estate of Ole Olson",
        estate_name="Estate of Ole Olson",
        estate_type="probate",
        grantor="Ole Olson",
        matter_id=matter.id,
        client_contact_id=contact.id,
    )
    db_session.add(contact)
    await db_session.flush()
    db_session.add(matter)
    await db_session.flush()
    db_session.add(estate)
    await db_session.flush()
    raw = secrets.token_urlsafe(32)
    invite = ClientPortalInvite(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        matter_id=matter.id,
        contact_id=contact.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        email=contact.email,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    entitlement = TenantPluginEntitlement(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        plugin_name="trust-estate-legal",
        status="purchased",
    )
    db_session.add_all([invite, entitlement])
    await db_session.commit()
    token = create_matter_portal_token(
        tenant_id=str(test_tenant.id),
        matter_id=str(matter.id),
        contact_id=str(contact.id),
        email=contact.email,
        invite_id=str(invite.id),
    )
    return {
        "contact": contact,
        "matter": matter,
        "estate": estate,
        "invite": invite,
        "entitlement": entitlement,
        "headers": {
            "Cookie": f"{CLIENT_PORTAL_COOKIE_NAME}={token}",
            "Authorization": "",
        },
    }


ASSET = {
    "name": "Checking at Gate City Bank",
    "category": "bank_account",
    "ownership_type": "sole",
    "approximate_value": "$12,500",
    "institution": "Gate City Bank",
}


@pytest.mark.asyncio
async def test_the_inventory_is_locked_until_appointment_and_then_accepts_items(
    client, db_session, estate_portal
):
    fixture = estate_portal
    view = await client.get(f"{PORTAL}/estate", headers=fixture["headers"])
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["decedent_name"] == "Ole Olson"
    assert body["inventory_open"] is False
    assert body["assets"] == []
    assert body["categories"][0]["key"] == "bank_account"

    locked = await client.post(
        f"{PORTAL}/estate/assets", json=ASSET, headers=fixture["headers"]
    )
    assert locked.status_code == 409

    fixture["estate"].appointment_date = date(2025, 3, 31)
    await db_session.commit()
    added = await client.post(
        f"{PORTAL}/estate/assets", json=ASSET, headers=fixture["headers"]
    )
    assert added.status_code == 201, added.text
    row = added.json()["assets"][0]
    assert row["name"] == "Checking at Gate City Bank"
    assert row["approximate_value"] == "12,500.00"
    assert row["verification_status"] == "unverified"
    assert row["editable"] is True

    stored = await db_session.scalar(
        select(EstateAsset).where(EstateAsset.id == uuid.UUID(row["id"]))
    )
    assert stored.source == "client_portal"
    assert stored.is_probate is True
    assert stored.submitted_at is not None

    changed = await client.patch(
        f"{PORTAL}/estate/assets/{row['id']}",
        json={**ASSET, "approximate_value": "about 13k", "ownership_type": "joint"},
        headers=fixture["headers"],
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["assets"][0]["approximate_value"] == "13,000.00"

    bad = await client.post(
        f"{PORTAL}/estate/assets",
        json={**ASSET, "approximate_value": "lots"},
        headers=fixture["headers"],
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_staff_can_open_the_inventory_early_and_verified_rows_become_read_only(
    client, db_session, estate_portal
):
    fixture = estate_portal
    fixture["estate"].probate_facts = {"inventory_open": True}
    await db_session.commit()
    added = await client.post(
        f"{PORTAL}/estate/assets", json=ASSET, headers=fixture["headers"]
    )
    assert added.status_code == 201, added.text
    asset_id = added.json()["assets"][0]["id"]

    verified = await client.post(
        f"{STAFF}/estates/{fixture['estate'].id}/assets/{asset_id}/verify",
        json={"verification_status": "verified", "note": "Matches the statement"},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verification_status"] == "verified"
    assert verified.json()["source"] == "client_portal"
    events = (
        (
            await db_session.execute(
                select(EstateEvent).where(EstateEvent.estate_id == fixture["estate"].id)
            )
        )
        .scalars()
        .all()
    )
    assert any("Asset verified" in event.title for event in events)

    refused = await client.patch(
        f"{PORTAL}/estate/assets/{asset_id}", json=ASSET, headers=fixture["headers"]
    )
    assert refused.status_code == 409
    view = await client.get(f"{PORTAL}/estate", headers=fixture["headers"])
    assert view.json()["assets"][0]["editable"] is False


@pytest.mark.asyncio
async def test_the_overlay_fails_closed(
    client, db_session, estate_portal, test_tenant, test_user
):
    fixture = estate_portal
    # Another firm's estate, another client, or no add-on: the portal says nothing.
    await db_session.delete(fixture["entitlement"])
    await db_session.commit()
    assert (
        await client.get(f"{PORTAL}/estate", headers=fixture["headers"])
    ).status_code == 404

    db_session.add(
        TenantPluginEntitlement(
            id=uuid.uuid4(),
            tenant_id=test_tenant.id,
            plugin_name="trust-estate-legal",
            status="purchased",
        )
    )
    other = Contact(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        first_name="Bob",
        last_name="Olson",
        email="bob@example.com",
    )
    db_session.add(other)
    await db_session.flush()
    fixture["estate"].client_contact_id = other.id
    await db_session.commit()
    assert (
        await client.get(f"{PORTAL}/estate", headers=fixture["headers"])
    ).status_code == 404

    fixture["estate"].client_contact_id = None  # falls back to the matter's client
    await db_session.commit()
    assert (
        await client.get(f"{PORTAL}/estate", headers=fixture["headers"])
    ).status_code == 200

    db_session.add(
        Estate(
            id=uuid.uuid4(),
            tenant_id=test_tenant.id,
            title="Second estate",
            estate_name="Second estate",
            matter_id=fixture["matter"].id,
            client_contact_id=fixture["contact"].id,
        )
    )
    await db_session.commit()
    assert (
        await client.get(f"{PORTAL}/estate", headers=fixture["headers"])
    ).status_code == 404
