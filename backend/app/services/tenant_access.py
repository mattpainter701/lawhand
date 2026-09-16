"""What a firm may reach while its trial runs, after it ends, and once it pays.

A firm on a trial carries ``Tenant.expires_at``: public signup and the
operator trial editor set it, and paying through Helcim clears it (see
``platform_billing.end_trial_when_paid``). Demo workspaces use the same column
but are synthetic tenants and follow none of the trial rules below.

* An expired trial is a hard stop except for paying: the firm can still sign
  in and reach ``/api/auth/me`` and the billing routes, and every other route
  keeps refusing it. Without this the only screen that could end the lockout
  was itself locked.
* Premium AI needs a firm that is not synthetic. It is withheld during a
  trial unless a platform operator explicitly sponsors it for that firm.
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.models.tenant import SYNTHETIC_BILLING_TIERS, Tenant
from app.services.tenant_state import require_active_tenant

# Deliberately narrow: seeing account state and paying. Nothing that reads or
# writes firm data belongs here.
EXPIRED_TRIAL_ALLOWED_PATHS = frozenset({"/api/auth/me", "/api/billing/status"})
EXPIRED_TRIAL_ALLOWED_PREFIXES = ("/api/billing/subscription/",)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _is_synthetic(tenant) -> bool:
    return getattr(tenant, "billing_tier", None) in SYNTHETIC_BILLING_TIERS


def trial_expired(tenant, now: datetime | None = None) -> bool:
    expires_at = getattr(tenant, "expires_at", None)
    if expires_at is None:
        return False
    return _as_utc(expires_at) <= (now or datetime.now(timezone.utc))


def access_state(tenant, now: datetime | None = None) -> str:
    """``trial_expired``, ``trial``, or ``active`` for the browser to act on.

    Demo workspaces report ``active``: their expiry is a demo session, which
    has its own banner, not a trial the firm can convert.
    """
    if (
        tenant is None
        or _is_synthetic(tenant)
        or getattr(tenant, "expires_at", None) is None
    ):
        return "active"
    return "trial_expired" if trial_expired(tenant, now) else "trial"


def allows_expired_trial(path: str) -> bool:
    return path in EXPIRED_TRIAL_ALLOWED_PATHS or any(
        path.startswith(prefix) for prefix in EXPIRED_TRIAL_ALLOWED_PREFIXES
    )


def require_sign_in_tenant(tenant):
    """Like ``require_active_tenant``, but let an expired trial through to pay.

    Only an active, non-synthetic firm whose sole problem is an elapsed trial
    passes. An inactive firm, a missing one, or an expired demo workspace is
    refused exactly as before.
    """
    if (
        tenant is not None
        and bool(getattr(tenant, "is_active", False))
        and not _is_synthetic(tenant)
        and trial_expired(tenant)
    ):
        return tenant
    return require_active_tenant(tenant)


def tenant_allows_premium_ai(tenant) -> bool:
    """Fail closed unless the firm is paid or has an explicit trial grant."""
    if tenant is None or _is_synthetic(tenant):
        return False
    return (
        getattr(tenant, "expires_at", None) is None
        or bool(getattr(tenant, "premium_ai_trial_enabled", False))
    )


def user_may_use_premium_ai(user) -> bool:
    """Premium-AI decision for a caller that already holds the firm.

    Only for a user whose ``tenant`` relationship is loaded (``/auth/me``).
    Handlers with a session must use :func:`resolve_user_premium_ai`.
    """
    return bool(getattr(user, "premium_ai_enabled", False)) and (
        tenant_allows_premium_ai(getattr(user, "tenant", None))
    )


async def tenant_allows_premium_ai_by_id(db, tenant_id) -> bool:
    if tenant_id is None:
        return False
    return tenant_allows_premium_ai(
        await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    )


async def resolve_user_premium_ai(db, user) -> bool:
    """Premium-AI decision for a handler that holds a session.

    The firm is resolved from ``user.tenant_id`` when the ``tenant``
    relationship is not loaded. A handler's user object may legitimately carry
    only the id — chat builds one from the verified token — so refusing on the
    missing relationship would turn premium off for a paid firm rather than
    answer the question that was asked.
    """
    if not bool(getattr(user, "premium_ai_enabled", False)):
        return False
    tenant = getattr(user, "tenant", None)
    if tenant is not None:
        return tenant_allows_premium_ai(tenant)
    return await tenant_allows_premium_ai_by_id(db, getattr(user, "tenant_id", None))
