"""LawHand-to-firm Helcim subscriptions. Never touches matter invoices or QBO.

Official contracts: devdocs.helcim.com/docs/recurring-api and /reference/subscription-create.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from functools import wraps
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from app.config import get_settings
from app.database import set_tenant_context
from app.models.platform_subscription import PlatformSubscription
from app.models.tenant import SYNTHETIC_BILLING_TIERS, Tenant, TenantSettings
from app.services.token_vault import decrypt_token, encrypt_token

settings = get_settings()
logger = logging.getLogger(__name__)


def rollback_on_error(function):
    @wraps(function)
    async def guarded(db, *args, **kwargs):
        try:
            return await function(db, *args, **kwargs)
        except BaseException:
            # Release row locks before the API error logger inserts a record
            # with a foreign key to this firm. Committed enrollment intent
            # survives this rollback and remains safe to reconcile.
            await db.rollback()
            raise

    return guarded


async def request_helcim(method, path, *, payload=None, params=None):
    if not settings.HELCIM_API_TOKEN:
        raise HTTPException(503, "LawHand subscription billing is not configured yet")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(
                method,
                "https://api.helcim.com/v2/" + path,
                headers={"api-token": settings.HELCIM_API_TOKEN},
                json=payload,
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            if (
                not isinstance(data, dict)
                or data.get("status") == "error"
                or data.get("errors")
            ):
                raise ValueError("Invalid provider response")
            return data
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            502,
            "Helcim is unavailable or rejected the request. Review billing status before retrying a subscription change.",
        ) from exc


def single(data):
    value = data.get("data", data)
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, dict):
        raise HTTPException(502, "Helcim returned an unexpected subscription response")
    return value


async def subscription_offer(tenant):
    if not settings.HELCIM_PAYMENT_PLAN_ID:
        raise HTTPException(503, "LawHand's Helcim subscription plan is not configured")
    plan = single(
        await request_helcim("GET", f"payment-plans/{settings.HELCIM_PAYMENT_PLAN_ID}")
    )
    if (
        plan.get("status") != "active"
        or plan.get("type") != "subscription"
        or plan.get("termType") != "forever"
        or plan.get("currency") not in ("USD", "CAD")
    ):
        raise HTTPException(
            503, "The configured LawHand subscription plan needs review"
        )
    # Initial launch uses the existing card-based subscription workflow. Bank
    # authorization and settlement must be separately verified before enabling ACH.
    if plan.get("paymentMethod") != "card":
        raise HTTPException(503, "Configure a card-enabled LawHand subscription plan")
    seats = max(tenant.flat_seat_count or 0, 1)
    try:
        amounts = [
            Decimal(str(plan.get(key, 0))) for key in ("recurringAmount", "setupAmount")
        ]
        if any(
            not value.is_finite() or value < 0 or value > Decimal("999999.99")
            for value in amounts
        ) or amounts[0] * seats > Decimal("999999.99"):
            raise ValueError()
        if int(plan["id"]) != settings.HELCIM_PAYMENT_PLAN_ID or plan.get("addOnIds"):
            raise ValueError()
    except (ValueError, ArithmeticError, TypeError, KeyError):
        raise HTTPException(503, "The configured subscription price needs review")
    try:
        helcim_trial_days = int(plan.get("freeTrialPeriod") or 0)
    except (TypeError, ValueError):
        raise HTTPException(503, "The configured subscription plan needs review")
    if helcim_trial_days:
        # LawHand runs the trial itself from signup. A Helcim trial on top would
        # start a second free period on the day the firm subscribes.
        raise HTTPException(
            503,
            "The LawHand subscription plan must not include a Helcim free trial",
        )
    offer = {
        "plan_id": int(plan["id"]),
        "name": plan.get("name", "LawHand subscription"),
        "currency": plan["currency"],
        "seats": seats,
        "unit_amount": str(
            Decimal(str(plan["recurringAmount"])).quantize(Decimal("0.01"))
        ),
        "recurring_amount": str(
            (Decimal(str(plan["recurringAmount"])) * seats).quantize(Decimal("0.01"))
        ),
        "setup_amount": str(
            Decimal(str(plan.get("setupAmount", 0))).quantize(Decimal("0.01"))
        ),
        "billing_period": plan.get("billingPeriod"),
        "billing_period_increments": plan.get("billingPeriodIncrements", 1),
        "billing_day": plan.get("dateBilling"),
        "trial_days": 0,
        "proration": plan.get("isProrated", "no"),
        "tax_type": plan.get("taxType"),
        "tax_calculation": plan.get("taxCalculation"),
    }
    offer["fingerprint"] = hashlib.sha256(
        json.dumps(offer, sort_keys=True).encode()
    ).hexdigest()
    return offer


async def locked_subscription(db, tenant_id):
    # Lock the existing tenant even before a subscription row exists.
    await set_tenant_context(db, str(tenant_id))
    tenant = await db.scalar(
        select(Tenant)
        .where(Tenant.id == tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not tenant:
        raise HTTPException(404, "Firm not found")
    if tenant.billing_tier in SYNTHETIC_BILLING_TIERS:
        raise HTTPException(403, "Demo workspaces cannot manage paid subscriptions")
    row = await db.scalar(
        select(PlatformSubscription)
        .where(PlatformSubscription.tenant_id == tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row:
        row = PlatformSubscription(tenant_id=tenant_id, status="none", phase="idle")
        db.add(row)
        await db.flush()
    return tenant, row


def verify_response(data, signature, secret):
    value = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    return hmac.compare_digest(
        hashlib.sha256((value + secret).encode()).hexdigest(), signature
    )


def verify_event(body, headers):
    try:
        timestamp = headers.get("webhook-timestamp", "")
        if abs(time.time() - int(timestamp)) > 300 or not settings.HELCIM_WEBHOOK_TOKEN:
            return False
        event_id = headers.get("webhook-id", "")
        if not event_id or len(event_id) > 200:
            return False
        key = base64.b64decode(settings.HELCIM_WEBHOOK_TOKEN, validate=True)
        message = event_id.encode() + b"." + timestamp.encode() + b"." + body
        expected = (
            "v1,"
            + base64.b64encode(hmac.new(key, message, hashlib.sha256).digest()).decode()
        )
        return any(
            hmac.compare_digest(expected, sig)
            for sig in headers.get("webhook-signature", "").split()
        )
    except (ValueError, TypeError):
        return False


@rollback_on_error
async def begin_checkout(db, tenant_id, user, fingerprint, *, update_method=False):
    tenant, row = await locked_subscription(db, tenant_id)
    if row.phase in ("enrolling", "needs_review"):
        raise HTTPException(
            409,
            "A subscription change needs reconciliation. Refresh billing status before continuing.",
        )
    if (
        row.subscription_id
        and row.status not in ("cancelled", "term_ended", "none")
        and not update_method
    ):
        raise HTTPException(409, "This firm already has a subscription")
    if update_method and not row.customer_code:
        raise HTTPException(409, "No subscription customer exists yet")
    offer = None if update_method else await subscription_offer(tenant)
    if offer and offer["fingerprint"] != fingerprint:
        raise HTTPException(
            409,
            "The subscription offer changed. Review the current price before continuing.",
        )
    now = datetime.now(timezone.utc)
    if (
        row.checkout_token
        and row.checkout_expires_at
        and row.checkout_expires_at > now
        and row.phase == "checkout"
    ):
        if (row.offer or {}).get("update_method", False) != update_method or (
            offer and row.offer.get("fingerprint") != fingerprint
        ):
            raise HTTPException(
                409,
                "Another billing checkout is open. Complete it or wait for it to expire.",
            )
        return {"provider": "helcim", "checkout_token": row.checkout_token}
    code = row.customer_code or "LH" + tenant.id.hex
    payload = {
        "paymentType": "verify",
        "amount": 0,
        "currency": (offer or row.offer or {}).get("currency", "USD"),
        "paymentMethod": "cc",
        "setAsDefaultPaymentMethod": 1,
        "hideExistingPaymentDetails": 1,
        "confirmationScreen": True,
    }
    if row.customer_code and (row.snapshot or {}).get("customer_verified"):
        payload["customerCode"] = code
    else:
        payload["customerRequest"] = {
            "customerCode": code,
            "contactName": user.full_name or tenant.name,
            "businessName": tenant.company_name or tenant.name,
        }
    result = await request_helcim("POST", "helcim-pay/initialize", payload=payload)
    if not result.get("checkoutToken") or not result.get("secretToken"):
        raise HTTPException(502, "Helcim did not return a complete checkout")
    if row.status in ("cancelled", "term_ended") and not update_method:
        row.subscription_id = None
        row.status = "none"
    row.customer_code = code
    row.checkout_token = result["checkoutToken"]
    row.encrypted_secret = encrypt_token(result["secretToken"])
    row.checkout_expires_at = now + timedelta(minutes=60)
    row.offer = {**(offer or row.offer or {}), "update_method": update_method}
    row.phase = "checkout"
    if not update_method:
        row.consent_by, row.consent_at = user.id, now
    await db.commit()
    return {"provider": "helcim", "checkout_token": row.checkout_token}


def apply_subscription(tenant, row, subscription):
    if str(subscription.get("customerCode")) != row.customer_code:
        raise HTTPException(409, "Subscription customer does not match this firm")
    if str(subscription.get("paymentPlanId")) != str(
        (row.offer or {}).get("plan_id")
    ) or (row.subscription_id and str(subscription.get("id")) != row.subscription_id):
        raise HTTPException(409, "Subscription identity does not match this firm")
    row.subscription_id = str(subscription["id"])
    row.status = subscription.get("status", "unknown")
    failed = str(subscription.get("hasFailedPayments", "false")).lower() == "true"
    live = row.status in ("active", "term_ending")
    paid_or_trial = (
        int(subscription.get("timesBilled", 0)) > 0
        or int(subscription.get("freeTrialPeriod", 0)) > 0
    )
    row.phase = "active" if live else "idle"
    row.synced_at = datetime.now(timezone.utc)
    row.snapshot = {
        "customer_verified": True,
        "next_billing_date": subscription.get("dateBilling"),
        "recurring_amount": str(subscription.get("recurringAmount", "0")),
        "has_failed_payments": failed,
        "payments": [
            {
                key: item.get(key)
                for key in (
                    "id",
                    "amount",
                    "taxAmount",
                    "status",
                    "dateDue",
                    "dateProcessed",
                    "paymentNumber",
                )
            }
            for item in subscription.get("payments", [])
        ][-100:],
    }
    tenant.platform_billing_provider = "helcim"
    tenant.platform_customer_id = row.customer_code
    tenant.platform_subscription_status = "past_due" if failed else row.status
    if live and paid_or_trial and not failed:
        tenant.billing_tier = "flat"
        if (row.offer or {}).get("seats"):
            tenant.flat_seat_count = int(row.offer["seats"])
        tenant.mcp_billing_status = "active"
    elif failed:
        tenant.mcp_billing_status = "past_due"
    elif not live:
        tenant.billing_tier = "payg"
        tenant.mcp_billing_status = "suspended"
    else:
        # Live but nothing billed yet. "pending" was never a storable value:
        # ck_tenants_mcp_billing_status (migration 087) allows only disabled,
        # active, past_due and suspended, so this raised a CheckViolationError
        # on any migrated database and broke the whole subscription sync.
        # MCP access stays denied until something is actually paid, which is
        # what suspended already means to ensure_mcp_product_access.
        tenant.mcp_billing_status = "suspended"


async def end_trial_when_paid(db, tenant) -> bool:
    """Clear a trial once Helcim confirms a paid, healthy subscription.

    ``apply_subscription`` sets the tier and seats but never touched the trial,
    so a firm that paid on day ten was still locked out on day thirty and still
    refused premium AI. Only the confirmed-paid state ends it; a pending,
    failed, or cancelled subscription leaves the trial exactly as it was.
    Returns whether a trial was ended.
    """
    from app.services.trials import (
        TRIAL_ENDS_KEY,
        TRIAL_MARKER,
        TRIAL_STARTED_KEY,
        config_marks_trial,
    )

    if tenant.billing_tier != "flat" or tenant.mcp_billing_status != "active":
        return False
    settings_row = await db.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant.id)
    )
    config = dict((settings_row.custom_config if settings_row else None) or {})
    if tenant.expires_at is None and not (
        config_marks_trial(config) or TRIAL_ENDS_KEY in config
    ):
        return False

    now = datetime.now(timezone.utc)
    tenant.expires_at = None
    if settings_row is not None:
        config[TRIAL_MARKER] = False
        config.pop(TRIAL_ENDS_KEY, None)
        config.pop(TRIAL_STARTED_KEY, None)
        config["trial_converted_at"] = now.isoformat()
        settings_row.custom_config = config
    logger.info("Trial converted to paid subscription tenant_id=%s", tenant.id)
    return True


@rollback_on_error
async def refresh_subscription(db, tenant_id):
    tenant, row = await locked_subscription(db, tenant_id)
    if row.subscription_id:
        remote = single(
            await request_helcim(
                "GET",
                f"subscriptions/{row.subscription_id}",
                params={"includeSubObjects": "true"},
            )
        )
        apply_subscription(tenant, row, remote)
    elif row.phase in ("enrolling", "needs_review") and row.customer_code:
        response = await request_helcim(
            "GET",
            "subscriptions",
            params={
                "customerCode": row.customer_code,
                "paymentPlanId": (row.offer or {}).get("plan_id"),
                "limit": 100,
            },
        )
        matches = [
            s
            for s in response.get("data", [])
            if s.get("customerCode") == row.customer_code
            and s.get("status") in ("active", "term_ending")
        ]
        if len(matches) != 1:
            raise HTTPException(
                409,
                "Subscription enrollment is unresolved. Contact LawHand support; do not submit another subscription.",
            )
        apply_subscription(
            tenant,
            row,
            single(
                await request_helcim(
                    "GET",
                    f"subscriptions/{matches[0]['id']}",
                    params={"includeSubObjects": "true"},
                )
            ),
        )
    await end_trial_when_paid(db, tenant)
    await db.commit()
    return subscription_response(row)


@rollback_on_error
async def finish_checkout(db, tenant_id, checkout_token, data, signature):
    tenant, row = await locked_subscription(db, tenant_id)
    if (
        not row.checkout_token
        or not hmac.compare_digest(row.checkout_token, checkout_token)
        or not row.encrypted_secret
    ):
        raise HTTPException(400, "Unknown billing checkout")
    try:
        valid = verify_response(data, signature, decrypt_token(row.encrypted_secret))
    except (TypeError, ValueError):
        valid = False
    if (
        not valid
        or data.get("customerCode") != row.customer_code
        or data.get("status") != "APPROVED"
        or str(data.get("type", "")).lower() != "verify"
    ):
        raise HTTPException(400, "Payment-method verification failed")
    if row.phase in ("enrolling", "needs_review"):
        return await refresh_subscription(db, tenant_id)
    if row.phase == "active":
        return subscription_response(row)
    if row.phase != "checkout":
        raise HTTPException(409, "This checkout is no longer current")
    if row.checkout_expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            409, "Checkout expired. Review the subscription offer again."
        )
    row.snapshot = {**(row.snapshot or {}), "customer_verified": True}
    if (row.offer or {}).get("update_method"):
        row.phase = "active" if row.subscription_id else "idle"
        await db.commit()
        return subscription_response(row)
    offer = await subscription_offer(tenant)
    if offer["fingerprint"] != row.offer.get("fingerprint"):
        raise HTTPException(
            409, "The subscription offer changed. Review it again before subscribing."
        )
    row.phase = "enrolling"
    # Commit the intent BEFORE the potentially charging call. An ambiguous
    # response is reconciled by customer/plan; never blindly POST a second subscription.
    await db.commit()
    payload = {
        "subscriptions": [
            {
                "customerCode": row.customer_code,
                "paymentPlanId": offer["plan_id"],
                "dateActivated": datetime.now(ZoneInfo("America/Denver"))
                .date()
                .isoformat(),
                "paymentMethod": "card",
                "recurringAmount": float(Decimal(offer["recurring_amount"])),
                "useCustomSetupAmount": True,
                "setupAmount": float(Decimal(offer["setup_amount"])),
                "withFreeTrialPeriod": False,
            }
        ]
    }
    result = await request_helcim("POST", "subscriptions", payload=payload)
    tenant, row = await locked_subscription(db, tenant_id)
    if row.phase != "enrolling":
        # A callback may have reconciled the subscription and a later request
        # may already have cancelled it while the original POST was in flight.
        return await refresh_subscription(db, tenant_id)
    apply_subscription(tenant, row, single(result))
    await end_trial_when_paid(db, tenant)
    await db.commit()
    return subscription_response(row)


def subscription_response(row):
    return {
        "provider": "helcim",
        "subscription_status": row.status,
        "phase": row.phase,
        "has_customer": bool(row.customer_code),
        "has_subscription": bool(row.subscription_id),
        "details": row.snapshot or {},
        "offer": row.offer or {},
        "synced_at": row.synced_at,
    }


@rollback_on_error
async def cancel_subscription(db, tenant_id):
    tenant, row = await locked_subscription(db, tenant_id)
    if not row.subscription_id:
        raise HTTPException(409, "No subscription to cancel")
    result = await request_helcim(
        "PATCH",
        "subscriptions",
        payload={
            "subscriptions": [{"id": int(row.subscription_id), "status": "cancelled"}]
        },
    )
    apply_subscription(tenant, row, single(result))
    await db.commit()
    return subscription_response(row)


async def reconcile_tenant_subscription(db, tenant_id):
    await set_tenant_context(db, str(tenant_id))
    row = await db.scalar(
        select(PlatformSubscription).where(PlatformSubscription.tenant_id == tenant_id)
    )
    if row and (row.subscription_id or row.phase in ("enrolling", "needs_review")):
        await refresh_subscription(db, tenant_id)
