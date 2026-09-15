"""What a firm may reach while its trial runs, after it ends, and once it pays.

A firm on a trial carries ``Tenant.expires_at``: public signup and the
operator trial editor set it, and paying through Helcim clears it (see
``platform_billing.end_trial_when_paid``). Demo workspaces use the same column
but are synthetic tenants and follow none of the trial rules below.

* An expired trial is a hard stop except for paying: the firm can still sign
  in and reach ``/api/auth/me`` and the billing routes, and every other route
  keeps refusing it. Without this the only screen that could end the lockout
  was itself locked.
* Premium AI needs a firm that is not on a trial and is not synthetic.
"""

from datetime import datetime, timezone

from app.models.tenant import SYNTHETIC_BILLING_TIERS
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
    """Fail closed: no firm, a synthetic firm, or any trial means no premium AI."""
    if tenant is None or _is_synthetic(tenant):
        return False
    return getattr(tenant, "expires_at", None) is None


def user_may_use_premium_ai(user) -> bool:
    return bool(getattr(user, "premium_ai_enabled", False)) and (
        tenant_allows_premium_ai(getattr(user, "tenant", None))
    )
