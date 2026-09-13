"""Provider isolation, subscription consent, and ambiguous-charge recovery."""

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.platform_subscription import PlatformSubscription
from app.services import platform_billing as service
from app.routers import billing


@pytest.fixture(autouse=True)
def helcim(monkeypatch):
    monkeypatch.setattr(service.settings, "PLATFORM_BILLING_PROVIDER", "helcim")
    monkeypatch.setattr(service.settings, "HELCIM_API_TOKEN", "test-token")
    monkeypatch.setattr(service.settings, "HELCIM_PAYMENT_PLAN_ID", 7)


def plan(**changes):
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


def remote(code, **changes):
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


@pytest.mark.asyncio
async def test_offer_is_provider_priced_and_rejects_unsupported_plans(
    test_tenant, monkeypatch
):
    test_tenant.flat_seat_count = 3
    request = AsyncMock(return_value=plan())
    monkeypatch.setattr(service, "request_helcim", request)
    offer = await service.subscription_offer(test_tenant)
    assert offer["recurring_amount"] == "150.00"
    assert offer["setup_amount"] == "10.00"
    for changes in (
        {"id": 8},
        {"recurringAmount": "NaN"},
        {"recurringAmount": -1},
        {"paymentMethod": "bank"},
        {"addOnIds": [12]},
        {"status": "inactive"},
    ):
        request.return_value = plan(**changes)
        with pytest.raises(HTTPException) as error:
            await service.subscription_offer(test_tenant)
        assert error.value.status_code == 503


def test_verification_binds_exact_signed_payload_and_webhook_time(monkeypatch):
    data = {"customerCode": "LHtest", "name": "François"}
    digest = hashlib.sha256(
        (json.dumps(data, ensure_ascii=True, separators=(",", ":")) + "secret").encode()
    ).hexdigest()
    assert service.verify_response(data, digest, "secret")
    assert not service.verify_response(
        {**data, "customerCode": "other"}, digest, "secret"
    )
    key = b"test-webhook-key"
    monkeypatch.setattr(
        service.settings, "HELCIM_WEBHOOK_TOKEN", base64.b64encode(key).decode()
    )
    timestamp = str(int(time.time()))
    body = b'{"id":"15","type":"cardTransaction"}'
    signature = base64.b64encode(
        hmac.new(
            key, b"evt." + timestamp.encode() + b"." + body, hashlib.sha256
        ).digest()
    ).decode()
    headers = {
        "webhook-id": "evt",
        "webhook-timestamp": timestamp,
        "webhook-signature": "v1," + signature,
    }
    assert service.verify_event(body, headers)
    assert not service.verify_event(body + b" ", headers)
    assert not service.verify_event(body, {**headers, "webhook-timestamp": "1"})


def test_subscription_management_license_exemption_is_narrow():
    from starlette.requests import Request
    from app.middleware.tenant import _is_license_exempt

    def request(path):
        return Request({"type": "http", "method": "POST", "path": path, "headers": []})

    assert _is_license_exempt(request("/api/billing/subscription/checkout"))
    assert _is_license_exempt(request("/api/billing/status"))
    assert not _is_license_exempt(request("/api/billing/invoices/generate"))


@pytest.mark.asyncio
async def test_view_only_permission_cannot_change_subscription(monkeypatch):
    from types import SimpleNamespace
    from app.routers import platform_billing as routes
    from app.services import rbac_service

    user = SimpleNamespace(id="user", role="user")
    monkeypatch.setattr(routes, "require_finance_admin", AsyncMock(return_value=user))
    monkeypatch.setattr(
        rbac_service, "get_user_capabilities", AsyncMock(return_value={"view_billing"})
    )
    with pytest.raises(HTTPException) as error:
        await routes.require_subscription_manager(None, None)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_helcim_access_needs_customer_and_no_stripe_delivery(monkeypatch):
    from types import SimpleNamespace
    from app.services import mcp_product

    monkeypatch.setattr(service.settings, "MCP_PRODUCT_ENABLED", True)
    tenant = SimpleNamespace(
        is_active=True,
        mcp_entitlement_status="enabled",
        mcp_billing_status="active",
        platform_billing_provider="helcim",
        platform_customer_id="firm",
    )
    mcp_product.ensure_mcp_product_access(tenant)
    tenant.platform_customer_id = None
    with pytest.raises(HTTPException) as error:
        mcp_product.ensure_mcp_product_access(tenant)
    assert error.value.status_code == 402
    with pytest.raises(RuntimeError, match="Legacy Stripe"):
        await mcp_product.deliver_mcp_meter_event({})


@pytest.mark.asyncio
async def test_checkout_never_repeats_uncertain_subscription_create(
    db_session, test_tenant, test_user, monkeypatch
):
    code = "LH" + test_tenant.id.hex

    async def provider(method, path, **kwargs):
        if path.startswith("payment-plans/"):
            return plan()
        if path == "helcim-pay/initialize":
            assert kwargs["payload"]["paymentType"] == "verify"
            assert kwargs["payload"]["amount"] == 0
            return {"checkoutToken": "checkout-test", "secretToken": "proof-secret"}
        if method == "POST" and path == "subscriptions":
            raise HTTPException(502, "Uncertain response")
        if path == "subscriptions":
            return {"data": [remote(code)]}
        if path == "subscriptions/9":
            return remote(code)
        raise AssertionError(path)

    request = AsyncMock(side_effect=provider)
    monkeypatch.setattr(service, "request_helcim", request)
    offer = await service.subscription_offer(test_tenant)
    with pytest.raises(HTTPException) as changed:
        await service.begin_checkout(db_session, test_tenant.id, test_user, "old-price")
    assert changed.value.status_code == 409
    await db_session.refresh(test_tenant)
    await db_session.refresh(test_user)
    result = await service.begin_checkout(
        db_session, test_tenant.id, test_user, offer["fingerprint"]
    )
    assert (
        await service.begin_checkout(
            db_session, test_tenant.id, test_user, offer["fingerprint"]
        )
        == result
    )
    assert (
        sum(call.args[1] == "helcim-pay/initialize" for call in request.call_args_list)
        == 1
    )
    data = {"customerCode": code, "status": "APPROVED", "type": "verify"}
    signature = hashlib.sha256(
        (json.dumps(data, separators=(",", ":")) + "proof-secret").encode()
    ).hexdigest()
    with pytest.raises(HTTPException) as uncertain:
        await service.finish_checkout(
            db_session, test_tenant.id, result["checkout_token"], data, signature
        )
    assert uncertain.value.status_code == 502
    await db_session.refresh(test_tenant)
    await db_session.refresh(test_user)
    row = await db_session.scalar(
        select(PlatformSubscription).where(
            PlatformSubscription.tenant_id == test_tenant.id
        )
    )
    assert row.phase == "enrolling"
    assert "proof-secret" not in row.encrypted_secret
    response = await service.finish_checkout(
        db_session, test_tenant.id, result["checkout_token"], data, signature
    )
    assert response["subscription_status"] == "active"
    assert (
        sum(
            call.args[:2] == ("POST", "subscriptions")
            for call in request.call_args_list
        )
        == 1
    )
    assert test_tenant.platform_billing_provider == "helcim"
    assert test_tenant.billing_tier == "flat"
    assert test_tenant.flat_seat_count == offer["seats"]
    assert test_tenant.mcp_entitlement_status == "disabled"
    with pytest.raises(HTTPException):
        await service.begin_checkout(
            db_session, test_tenant.id, test_user, offer["fingerprint"]
        )


@pytest.mark.asyncio
async def test_signup_does_not_create_stripe_customer(
    db_session, test_tenant, monkeypatch
):
    monkeypatch.setattr(billing.settings, "STRIPE_SECRET_KEY", "unused-stripe-key")
    create = AsyncMock()
    monkeypatch.setattr(billing.stripe.Customer, "create", create)
    await billing.ensure_stripe_customer(test_tenant, db_session)
    create.assert_not_called()
    assert test_tenant.stripe_customer_id is None


def test_subscription_mismatch_cannot_change_entitlements(test_tenant):
    row = PlatformSubscription(
        tenant_id=test_tenant.id,
        customer_code="firm",
        subscription_id="9",
        offer={"plan_id": 7},
    )
    for changes in ({"customerCode": "other"}, {"paymentPlanId": 8}, {"id": 10}):
        with pytest.raises(HTTPException):
            service.apply_subscription(test_tenant, row, remote("firm", **changes))
    service.apply_subscription(
        test_tenant, row, remote("firm", hasFailedPayments="true")
    )
    assert test_tenant.mcp_billing_status == "past_due"
    service.apply_subscription(test_tenant, row, remote("firm", status="cancelled"))
    assert test_tenant.billing_tier == "payg"
    assert test_tenant.mcp_billing_status == "suspended"


@pytest.mark.asyncio
async def test_api_blocks_stripe_checkout_and_rejects_unsigned_events(client):
    response = await client.post("/api/billing/checkout-session")
    assert response.status_code == 409
    response = await client.post(
        "/api/billing/provider-events", json={"id": "15", "type": "cardTransaction"}
    )
    assert response.status_code == 400
    response = await client.put("/api/admin/billing", json={"billing_tier": "flat"})
    assert response.status_code == 409, response.text
    response = await client.post("/api/billing/portal")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_subscription_api_card_update_cancel_and_reconcile(
    client, db_session, test_tenant, monkeypatch
):
    code = "LH" + test_tenant.id.hex
    remote_state = remote(code)

    async def provider(method, path, **kwargs):
        if path.startswith("payment-plans/"):
            return plan()
        if path == "helcim-pay/initialize":
            return {"checkoutToken": "api-checkout", "secretToken": "api-secret"}
        if method == "PATCH":
            remote_state["status"] = "cancelled"
        return {"data": [dict(remote_state)]}

    monkeypatch.setattr(service, "request_helcim", AsyncMock(side_effect=provider))
    offer_response = await client.get("/api/billing/subscription/offer")
    assert offer_response.status_code == 200, offer_response.text
    offer = offer_response.json()
    checkout = await client.post(
        "/api/billing/subscription/checkout", json={"fingerprint": offer["fingerprint"]}
    )
    assert checkout.status_code == 200, checkout.text
    proof = {"customerCode": code, "status": "APPROVED", "type": "verify"}
    signature = hashlib.sha256(
        (json.dumps(proof, separators=(",", ":")) + "api-secret").encode()
    ).hexdigest()
    body = {"checkout_token": "api-checkout", "data": proof, "signature": signature}
    bad = await client.post(
        "/api/billing/subscription/complete", json={**body, "signature": "0" * 64}
    )
    assert bad.status_code == 400
    completed = await client.post("/api/billing/subscription/complete", json=body)
    assert completed.status_code == 200, completed.text
    replay = await client.post("/api/billing/subscription/complete", json=body)
    assert replay.status_code == 200
    updated = await client.post(
        "/api/billing/subscription/checkout", json={"update_method": True}
    )
    assert updated.status_code == 200, updated.text
    assert (
        await client.post("/api/billing/subscription/complete", json=body)
    ).status_code == 200
    status = await client.get("/api/billing/status")
    assert status.json()["provider"] == "helcim"
    assert "encrypted_secret" not in status.text
    assert "checkout_token" not in status.text
    refresh = await client.post("/api/billing/subscription/refresh")
    assert refresh.status_code == 200, refresh.text
    cancelled = await client.post("/api/billing/subscription/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["subscription_status"] == "cancelled"


@pytest.mark.asyncio
async def test_provider_http_errors_are_sanitized(monkeypatch):
    import httpx

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.request.side_effect = httpx.ConnectTimeout("secret provider details")
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client)
    with pytest.raises(HTTPException) as error:
        await service.request_helcim("GET", "subscriptions/9")
    assert error.value.status_code == 502
    assert "secret" not in error.value.detail
    monkeypatch.setattr(service.settings, "HELCIM_API_TOKEN", "")
    with pytest.raises(HTTPException) as error:
        await service.request_helcim("GET", "subscriptions/9")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_signed_webhook_resolves_customer_from_provider_only(
    client, db_session, test_tenant, monkeypatch
):
    code = "LH" + test_tenant.id.hex
    row = PlatformSubscription(
        tenant_id=test_tenant.id,
        customer_code=code,
        subscription_id="9",
        status="active",
        phase="active",
        offer={"plan_id": 7},
    )
    db_session.add(row)
    await db_session.commit()
    monkeypatch.setattr(service, "verify_event", lambda *args: True)
    request = AsyncMock(
        side_effect=[{"customerCode": code}, remote(code, hasFailedPayments="true")]
    )
    monkeypatch.setattr(service, "request_helcim", request)
    response = await client.post(
        "/api/billing/provider-events",
        json={"type": "cardTransaction", "id": "15", "tenant_id": "attacker"},
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(test_tenant)
    assert test_tenant.platform_subscription_status == "past_due"
    assert request.call_args_list[0].args == ("GET", "card-transactions/15")


@pytest.mark.asyncio
async def test_helcim_mcp_usage_does_not_enqueue_stripe(
    db_session, test_tenant, monkeypatch, client
):
    import uuid
    from app.models.mcp_product import MCPProductKey
    from app.services import mcp_product

    test_tenant.platform_billing_provider = "helcim"
    test_tenant.platform_customer_id = "LH" + test_tenant.id.hex
    key = MCPProductKey(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        name="usage",
        key_prefix="test",
        key_hash=uuid.uuid4().hex,
        unit_price_cents=75,
    )
    db_session.add(key)
    await db_session.commit()
    enqueue = AsyncMock()
    monkeypatch.setattr(mcp_product, "enqueue_job", enqueue)
    event = await mcp_product.record_mcp_usage(
        db=db_session,
        tenant_id=test_tenant.id,
        product_key_id=key.id,
        user_id=None,
        auth_type="product_key",
        transport="rest",
        tool_name="search",
        status_code=200,
        result_count=1,
    )
    assert event.metadata_json["platform_billing"] == {
        "provider": "helcim",
        "collection": "pending_review",
        "unit_price_cents": 75,
        "currency": "USD",
    }
    enqueue.assert_not_called()
    status = await client.get("/api/billing/status")
    assert status.status_code == 200, status.text
    assert status.json()["mcp_usage"]["estimated_charges_usd_30d"] == 0.75
