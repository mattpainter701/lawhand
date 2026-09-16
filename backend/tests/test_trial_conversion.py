"""A trial ends when the firm pays, an ended trial can still pay, and trials never get premium AI.

Before: paying through Helcim set the tier but never cleared ``expires_at``,
so a firm that paid on day ten was locked out on day thirty; an expired firm
could not sign in or reach billing to pay at all; a Helcim plan trial could
stack on LawHand's own; and premium AI was only blocked at the settings toggle.
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from app.models.platform_subscription import PlatformSubscription
from app.models.tenant import Tenant, TenantSettings
from app.models.user import User
from app.routers import auth as auth_router
from app.routers.chat import _premium_for_user
from app.services import platform_billing as service
from app.services import tenant_access

PASSWORD = "correct-horse-battery-staple-42"


@pytest.fixture(autouse=True)
def helcim(monkeypatch):
    monkeypatch.setattr(service.settings, "PLATFORM_BILLING_PROVIDER", "helcim")
    monkeypatch.setattr(service.settings, "HELCIM_API_TOKEN", "test-token")
    monkeypatch.setattr(service.settings, "HELCIM_PAYMENT_PLAN_ID", 7)


@pytest_asyncio.fixture(autouse=True)
async def _reset_auth_rate_limits(test_redis):
    for path in ("/api/auth/login", "/api/auth/refresh"):
        async for key in test_redis.scan_iter(f"rate:auth:{path}:*"):
            await test_redis.delete(key)
    yield


def _plan(**changes):
    return {
        "id": 7,
        "name": "LawHand",
        "status": "active",
        "type": "subscription",
        "termType": "forever",
        "currency": "USD",
        "paymentMethod": "card",
        "recurringAmount": 50,
        "setupAmount": 10,
        "billingPeriod": "monthly",
        "billingPeriodIncrements": 1,
        "dateBilling": "Sign-up",
        **changes,
    }


def _remote(code, **changes):
    return {
        "id": 9,
        "customerCode": code,
        "paymentPlanId": 7,
        "status": "active",
        "hasFailedPayments": "false",
        "timesBilled": 1,
        "freeTrialPeriod": 0,
        "recurringAmount": 50,
        "payments": [],
        **changes,
    }


async def _firm(
    db_session,
    *,
    days_left: int | None,
    is_active: bool = True,
    billing_tier: str = "payg",
    email: str | None = None,
):
    now = datetime.now(timezone.utc)
    expires_at = None if days_left is None else now + timedelta(days=days_left)
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Trial Firm",
        domain=f"trial-{uuid.uuid4().hex[:8]}.example",
        billing_tier=billing_tier,
        is_active=is_active,
        expires_at=expires_at,
    )
    config = {"plan": "full-platform"}
    if expires_at is not None:
        config.update(
            trial=True,
            trial_started_at=(expires_at - timedelta(days=30)).isoformat(),
            trial_ends_at=expires_at.isoformat(),
        )
    settings_row = TenantSettings(tenant_id=tenant.id, custom_config=config)
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=email or f"owner-{uuid.uuid4().hex[:6]}@trial.example",
        full_name="Firm Owner",
        role="admin",
        is_active=True,
        license_active=True,
        password_hash=auth_router._hash_password(PASSWORD),
    )
    db_session.add_all([tenant, settings_row, user])
    await db_session.commit()
    return tenant, settings_row, user


async def _subscribed(db_session, tenant):
    code = "LH" + tenant.id.hex
    db_session.add(
        PlatformSubscription(
            tenant_id=tenant.id,
            customer_code=code,
            subscription_id="9",
            status="active",
            phase="active",
            offer={"plan_id": 7, "seats": 1},
        )
    )
    await db_session.commit()
    return code


# ── Helcim never runs a second trial ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_offer_refuses_a_helcim_plan_with_its_own_trial(test_tenant, monkeypatch):
    request = AsyncMock(return_value=_plan(freeTrialPeriod=30))
    monkeypatch.setattr(service, "request_helcim", request)

    with pytest.raises(HTTPException) as refused:
        await service.subscription_offer(test_tenant)

    assert refused.value.status_code == 503
    assert "free trial" in refused.value.detail
    request.return_value = _plan()
    assert (await service.subscription_offer(test_tenant))["trial_days"] == 0


@pytest.mark.asyncio
async def test_checkout_never_asks_helcim_for_a_trial(
    db_session, test_tenant, test_user, monkeypatch
):
    code = "LH" + test_tenant.id.hex
    created: list[dict] = []

    async def provider(method, path, **kwargs):
        if path.startswith("payment-plans/"):
            return _plan()
        if path == "helcim-pay/initialize":
            return {"checkoutToken": "checkout-trial", "secretToken": "proof-secret"}
        if method == "POST" and path == "subscriptions":
            created.append(kwargs["payload"])
            return _remote(code)
        raise AssertionError(path)

    monkeypatch.setattr(service, "request_helcim", AsyncMock(side_effect=provider))
    offer = await service.subscription_offer(test_tenant)
    checkout = await service.begin_checkout(
        db_session, test_tenant.id, test_user, offer["fingerprint"]
    )
    data = {"customerCode": code, "status": "APPROVED", "type": "verify"}
    signature = hashlib.sha256(
        (json.dumps(data, separators=(",", ":")) + "proof-secret").encode()
    ).hexdigest()

    await service.finish_checkout(
        db_session, test_tenant.id, checkout["checkout_token"], data, signature
    )

    assert created[0]["subscriptions"][0]["withFreeTrialPeriod"] is False


# ── Paying ends the trial ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_paying_ends_the_trial(db_session, monkeypatch):
    tenant, settings_row, _ = await _firm(db_session, days_left=10)
    code = await _subscribed(db_session, tenant)
    monkeypatch.setattr(
        service, "request_helcim", AsyncMock(return_value=_remote(code))
    )

    await service.refresh_subscription(db_session, tenant.id)

    await db_session.refresh(tenant)
    await db_session.refresh(settings_row)
    assert tenant.billing_tier == "flat"
    assert tenant.expires_at is None
    config = settings_row.custom_config
    assert config["trial"] is False
    assert "trial_ends_at" not in config
    assert config["trial_converted_at"]
    assert config["plan"] == "full-platform"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"hasFailedPayments": "true"},
        {"status": "cancelled"},
        {"timesBilled": 0},
    ],
    ids=["failed-payment", "cancelled", "not-yet-billed"],
)
async def test_unpaid_subscription_leaves_the_trial_running(
    db_session, monkeypatch, changes
):
    tenant, settings_row, _ = await _firm(db_session, days_left=10)
    expires_at = tenant.expires_at
    code = await _subscribed(db_session, tenant)
    monkeypatch.setattr(
        service, "request_helcim", AsyncMock(return_value=_remote(code, **changes))
    )

    await service.refresh_subscription(db_session, tenant.id)

    await db_session.refresh(tenant)
    await db_session.refresh(settings_row)
    assert tenant.expires_at == expires_at
    assert settings_row.custom_config["trial"] is True


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"hasFailedPayments": "true"},
        {"status": "cancelled"},
        {"timesBilled": 0},
    ],
    ids=["paid", "failed-payment", "cancelled", "not-yet-billed"],
)
def test_every_subscription_state_stores_a_permitted_billing_status(
    test_tenant, changes
):
    """ck_tenants_mcp_billing_status (migration 087) allows only these four.

    The live-but-unbilled branch wrote "pending", which no migrated database
    accepts, so a real subscription sync in that state raised
    CheckViolationError. create_all test databases carry no check constraints,
    which is why it survived locally until CI ran it.
    """
    row = PlatformSubscription(
        tenant_id=test_tenant.id,
        customer_code="firm",
        subscription_id="9",
        offer={"plan_id": 7, "seats": 1},
    )

    service.apply_subscription(test_tenant, row, _remote("firm", **changes))

    assert test_tenant.mcp_billing_status in {
        "disabled",
        "active",
        "past_due",
        "suspended",
    }


@pytest.mark.asyncio
async def test_paid_firm_that_never_had_a_trial_is_untouched(db_session, test_tenant):
    test_tenant.billing_tier = "flat"
    test_tenant.mcp_billing_status = "active"
    await db_session.commit()

    assert await service.end_trial_when_paid(db_session, test_tenant) is False
    assert (
        await db_session.scalar(
            select(TenantSettings).where(TenantSettings.tenant_id == test_tenant.id)
        )
        is None
    )


# ── An ended trial can pay and nothing else ──────────────────────────────────


@pytest.mark.asyncio
async def test_ended_trial_signs_in_and_reaches_only_account_and_billing(
    client, db_session
):
    _, _, user = await _firm(db_session, days_left=-1)

    login = await client.post(
        "/api/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text

    me = await client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["access_state"] == "trial_expired"
    assert me.json()["trial_ends_at"] is not None
    assert me.json()["premium_ai_available"] is False

    billing = await client.get("/api/billing/status")
    assert billing.status_code == 200, billing.text

    for path in ("/api/admin/users", "/api/matters"):
        refused = await client.get(path)
        assert refused.status_code == 403, (path, refused.text)
        assert refused.json()["detail"] == "Tenant access has expired"

    refreshed = await client.post("/api/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_active", "billing_tier"),
    [(False, "payg"), (True, "demo")],
    ids=["switched-off-firm", "expired-demo"],
)
async def test_inactive_firm_and_expired_demo_still_cannot_sign_in(
    client, db_session, is_active, billing_tier
):
    _, _, user = await _firm(
        db_session, days_left=-1, is_active=is_active, billing_tier=billing_tier
    )

    login = await client.post(
        "/api/auth/login", json={"email": user.email, "password": PASSWORD}
    )

    assert login.status_code == 403


@pytest.mark.asyncio
async def test_running_trial_reports_its_end_date(client, db_session):
    tenant, _, user = await _firm(db_session, days_left=12)

    login = await client.post(
        "/api/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    me = await client.get("/api/auth/me")

    assert login.status_code == 200, login.text
    assert me.json()["access_state"] == "trial"
    assert datetime.fromisoformat(
        me.json()["trial_ends_at"].replace("Z", "+00:00")
    ) == tenant.expires_at.replace(microsecond=tenant.expires_at.microsecond)
    assert me.json()["premium_ai_available"] is False


# ── Premium AI ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("tenant", "allowed"),
    [
        (SimpleNamespace(billing_tier="flat", expires_at=None), True),
        (
            SimpleNamespace(
                billing_tier="payg",
                expires_at=datetime.now(timezone.utc) + timedelta(days=5),
            ),
            False,
        ),
        (
            SimpleNamespace(
                billing_tier="payg",
                expires_at=datetime.now(timezone.utc) - timedelta(days=5),
            ),
            False,
        ),
        (SimpleNamespace(billing_tier="demo", expires_at=None), False),
        (None, False),
    ],
    ids=["paid", "trial", "ended-trial", "demo", "no-firm"],
)
def test_premium_ai_needs_a_paid_firm_even_when_the_user_flag_is_on(tenant, allowed):
    user = SimpleNamespace(premium_ai_enabled=True, tenant=tenant)

    assert tenant_access.user_may_use_premium_ai(user) is allowed


def test_premium_ai_still_needs_the_user_flag():
    user = SimpleNamespace(
        premium_ai_enabled=False,
        tenant=SimpleNamespace(billing_tier="flat", expires_at=None),
    )

    assert tenant_access.user_may_use_premium_ai(user) is False


class _TenantLookup:
    """Session double that resolves one firm, like db.scalar(select(Tenant))."""

    def __init__(self, tenant):
        self._tenant = tenant
        self.calls = 0

    async def scalar(self, _statement):
        self.calls += 1
        return self._tenant


@pytest.mark.asyncio
async def test_premium_resolves_the_firm_by_id_when_it_is_not_loaded():
    """The chat handler's user comes from the verified token and has no firm.

    Refusing on the missing relationship turned premium off mid-stream for a
    paid firm, which sent the request down an unmocked path and hung
    test_cancelled_stream_persists_a_retryable_assistant_turn.
    """
    db = _TenantLookup(SimpleNamespace(billing_tier="flat", expires_at=None))
    user = SimpleNamespace(premium_ai_enabled=True, tenant=None, tenant_id=uuid.uuid4())

    assert await tenant_access.resolve_user_premium_ai(db, user) is True
    assert await _premium_for_user(db, user, "draft a motion", True) is True
    assert db.calls == 2


@pytest.mark.asyncio
async def test_premium_refused_for_a_trial_firm_resolved_by_id():
    db = _TenantLookup(
        SimpleNamespace(
            billing_tier="payg",
            expires_at=datetime.now(timezone.utc) + timedelta(days=5),
        )
    )
    user = SimpleNamespace(premium_ai_enabled=True, tenant=None, tenant_id=uuid.uuid4())

    assert await tenant_access.resolve_user_premium_ai(db, user) is False
    assert await _premium_for_user(db, user, "draft a motion", True) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user", "expected_queries"),
    [
        (
            SimpleNamespace(
                premium_ai_enabled=False, tenant=None, tenant_id=uuid.uuid4()
            ),
            0,
        ),
        (SimpleNamespace(premium_ai_enabled=True, tenant=None, tenant_id=None), 0),
    ],
    ids=["flag-off-never-queries", "no-firm-at-all"],
)
async def test_premium_is_refused_without_querying_the_firm(user, expected_queries):
    db = _TenantLookup(SimpleNamespace(billing_tier="flat", expires_at=None))

    assert await tenant_access.resolve_user_premium_ai(db, user) is False
    assert db.calls == expected_queries


@pytest.mark.asyncio
async def test_a_standard_question_never_looks_up_the_firm():
    db = _TenantLookup(SimpleNamespace(billing_tier="flat", expires_at=None))
    user = SimpleNamespace(premium_ai_enabled=True, tenant=None, tenant_id=uuid.uuid4())

    assert await _premium_for_user(db, user, "what time is the hearing", False) is False
    assert db.calls == 0


def test_expired_trial_allowance_is_limited_to_account_and_billing_routes():
    allowed = ["/api/auth/me", "/api/billing/status", "/api/billing/subscription/offer"]
    refused = [
        "/api/matters",
        "/api/billing/invoices",
        "/api/billing/subscriptions",
        "/api/admin/users",
        "/api/auth/me/extra",
    ]

    assert all(tenant_access.allows_expired_trial(path) for path in allowed)
    assert not any(tenant_access.allows_expired_trial(path) for path in refused)
