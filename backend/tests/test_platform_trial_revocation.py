"""Platform operator revocation of a self-serve trial tenant.

The behaviour under test is deliberately narrow: deactivate every human login,
move its address to a tombstone so the original can register again, drop the
stored provider grant, and never touch a tenant that holds work product.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.external_import import ExternalSystemConnection
from app.models.operator_audit import OperatorAuditLog
from app.models.tenant import Tenant, TenantSettings
from app.models.tenant_credential import TenantCredential
from app.models.user import User
from tests.platform_auth_helpers import platform_headers


def _trial_tenant(*, tenant_id: uuid.UUID, active: bool = True) -> Tenant:
    now = datetime.now(timezone.utc)
    return Tenant(
        id=tenant_id,
        name="LawHand Gmail Trial",
        domain=f"lawhand-trial-{tenant_id.hex[:8]}",
        billing_tier="trial",
        is_active=active,
        expires_at=now + timedelta(days=14),
    )


def _trial_settings(tenant_id: uuid.UUID) -> TenantSettings:
    now = datetime.now(timezone.utc)
    return TenantSettings(
        tenant_id=tenant_id,
        custom_config={
            "trial": True,
            "trial_started_at": now.isoformat(),
            "trial_ends_at": (now + timedelta(days=14)).isoformat(),
        },
    )


def _human_user(*, tenant_id: uuid.UUID) -> User:
    return User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="getlawhand@gmail.com",
        full_name="Gmail Trial",
        role="admin",
        oauth_provider="google",
        oauth_subject="google-subject-abc",
        password_hash="hashed",
        is_active=True,
        license_active=True,
        principal_type="human",
    )


def _credential(tenant_id: uuid.UUID) -> TenantCredential:
    return TenantCredential(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider="google",
        encrypted_access_token="enc-access",
        is_active=True,
    )


@pytest.mark.asyncio
async def test_revoke_requires_write_scope(client, db_session):
    tenant = _trial_tenant(tenant_id=uuid.uuid4())
    user = _human_user(tenant_id=tenant.id)
    db_session.add_all([tenant, _trial_settings(tenant.id), user])
    await db_session.commit()

    response = await client.post(
        f"/api/platform/tenants/{tenant.id}/revoke",
        json={"confirm_email": "getlawhand@gmail.com"},
        headers=platform_headers(["platform:read"]),
    )

    assert response.status_code == 403
    await db_session.refresh(user)
    assert user.email == "getlawhand@gmail.com"
    assert user.is_active is True


@pytest.mark.asyncio
async def test_revoke_releases_login_and_revokes_provider_credential(
    client, db_session
):
    tenant = _trial_tenant(tenant_id=uuid.uuid4())
    user = _human_user(tenant_id=tenant.id)
    db_session.add_all(
        [tenant, _trial_settings(tenant.id), user, _credential(tenant.id)]
    )
    await db_session.commit()

    response = await client.post(
        f"/api/platform/tenants/{tenant.id}/revoke",
        json={"confirm_email": "getlawhand@gmail.com", "reason": "re-onboard test"},
        headers=platform_headers(["platform:write"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "revoked"
    assert body["released_emails"] == ["getlawhand@gmail.com"]
    assert body["users_revoked"] == 1
    assert body["credentials_revoked"] == 1

    await db_session.refresh(user)
    assert user.email != "getlawhand@gmail.com"
    assert user.email.endswith("@revoked.invalid")
    assert user.is_active is False
    assert user.license_active is False
    assert user.oauth_subject is None
    assert user.password_hash is None

    remaining = await db_session.scalar(
        select(func.count(TenantCredential.id)).where(
            TenantCredential.tenant_id == tenant.id
        )
    )
    assert remaining == 0

    await db_session.refresh(tenant)
    assert tenant.is_active is False
    assert tenant.expires_at <= datetime.now(timezone.utc)

    config = await db_session.scalar(
        select(TenantSettings.custom_config).where(
            TenantSettings.tenant_id == tenant.id
        )
    )
    assert config["trial"] is False
    assert "revoked_at" in config

    audit = await db_session.scalar(
        select(OperatorAuditLog).where(
            OperatorAuditLog.action == "trial.revoked",
            OperatorAuditLog.resource_id == str(tenant.id),
        )
    )
    assert audit is not None
    assert audit.actor_id == "test-operator"


@pytest.mark.asyncio
async def test_revoke_refuses_when_work_product_exists(client, db_session):
    tenant = _trial_tenant(tenant_id=uuid.uuid4())
    user = _human_user(tenant_id=tenant.id)
    db_session.add_all([tenant, _trial_settings(tenant.id), user])
    await db_session.flush()
    db_session.add(
        ExternalSystemConnection(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            provider="tabs3",
            external_key="firm-1",
            display_name="Tabs3",
        )
    )
    await db_session.commit()

    response = await client.post(
        f"/api/platform/tenants/{tenant.id}/revoke",
        json={"confirm_email": "getlawhand@gmail.com"},
        headers=platform_headers(["platform:write"]),
    )

    assert response.status_code == 409
    assert "work product" in response.json()["detail"]
    await db_session.refresh(user)
    assert user.is_active is True
    assert user.email == "getlawhand@gmail.com"


@pytest.mark.asyncio
async def test_revoke_refuses_on_confirmation_mismatch(client, db_session):
    tenant = _trial_tenant(tenant_id=uuid.uuid4())
    user = _human_user(tenant_id=tenant.id)
    db_session.add_all([tenant, _trial_settings(tenant.id), user])
    await db_session.commit()

    response = await client.post(
        f"/api/platform/tenants/{tenant.id}/revoke",
        json={"confirm_email": "someone-else@example.com"},
        headers=platform_headers(["platform:write"]),
    )

    assert response.status_code == 409
    assert "does not match" in response.json()["detail"]
    await db_session.refresh(user)
    assert user.is_active is True


@pytest.mark.asyncio
async def test_revoke_refuses_an_active_paid_tenant(client, db_session):
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Paying Firm",
        domain="payingfirm.com",
        billing_tier="payg",
        is_active=True,
    )
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="owner@payingfirm.com",
        role="admin",
        is_active=True,
        license_active=True,
        principal_type="human",
    )
    db_session.add_all([tenant, user])
    await db_session.commit()

    response = await client.post(
        f"/api/platform/tenants/{tenant.id}/revoke",
        json={"confirm_email": "owner@payingfirm.com"},
        headers=platform_headers(["platform:write"]),
    )

    assert response.status_code == 409
    assert "not an active trial" in response.json()["detail"]
    await db_session.refresh(user)
    assert user.is_active is True


@pytest.mark.asyncio
async def test_revoke_refuses_disposable_demo(client, db_session):
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Demo",
        domain=f"demo-{uuid.uuid4().hex[:8]}.demo.invalid",
        billing_tier="demo",
        is_active=True,
    )
    user = _human_user(tenant_id=tenant.id)
    db_session.add_all([tenant, user])
    await db_session.commit()

    response = await client.post(
        f"/api/platform/tenants/{tenant.id}/revoke",
        json={"confirm_email": "getlawhand@gmail.com"},
        headers=platform_headers(["platform:write"]),
    )

    assert response.status_code == 409
    assert "demo panel" in response.json()["detail"]


@pytest.mark.asyncio
async def test_revoke_returns_not_found_for_unknown_tenant(client):
    response = await client.post(
        f"/api/platform/tenants/{uuid.uuid4()}/revoke",
        json={"confirm_email": "getlawhand@gmail.com"},
        headers=platform_headers(["platform:write"]),
    )

    assert response.status_code == 404
