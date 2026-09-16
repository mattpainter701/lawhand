"""Operator-authorized revocation of a self-serve trial tenant.

A revoked trial is deliberately **not** a deleted tenant. The tenant's
compliance ledger (``tenant_agreement_acceptances``) is append-only by design
and carries a ``RESTRICT`` foreign key to ``tenants``, so a hard delete is
neither supported nor something an operator shortcut should attempt. What a
re-onboarding test actually needs is for the login address to stop being taken.

This service therefore:

* refuses when the tenant holds real work product, so it can never be used to
  quietly destroy a live firm's data;
* deactivates every human login in the tenant and moves each address to a
  unique, non-deliverable tombstone so the original address can register again;
* removes the stored provider credential (Google Drive / Microsoft 365) so the
  previous grant cannot be replayed; and
* leaves the tenant row, its append-only agreement evidence, and any provider
  Drive/OneDrive content untouched, with an operator audit recorded by the
  caller.

Hard deletion of an expired disposable *demo* is a different operation and
stays on ``services.demo_purge``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base
from app.models.tenant import Tenant, TenantSettings
from app.models.tenant_credential import TenantCredential
from app.models.user import User
from app.services.trials import TRIAL_MARKER, config_marks_trial

# Any row in these tables means the tenant is doing — or is set up to do — real
# customer work. Revocation is fail-closed: refuse and let a human decide,
# rather than deactivate a firm that already has matters or documents.
_SUBSTANTIVE_TABLES: tuple[str, ...] = (
    "matters",
    "documents",
    "matter_documents",
    "tasks",
    "invoices",
    "payments",
    "time_entries",
    "expenses",
    "retainers",
    "retainer_transactions",
    "trust_accounts",
    "trust_transactions",
    "engagement_packets",
    "signature_requests",
    "research_workspaces",
    "studio_drafts",
    "intake_submissions",
    "inbound_emails",
    "qbo_integrations",
    "external_system_connections",
)

# Operators only revoke a tenant that never became a paying customer: an
# explicit trial marker, the ``trial`` billing tier used by the current signup
# path, or an already-inactive tenant carrying a bounded expiry.
_TRIAL_TIERS = frozenset({"trial"})


class TrialRevocationRefused(RuntimeError):
    """Raised when a tenant is not eligible for operator revocation."""


def _tombstone_email(user_id: uuid.UUID) -> str:
    return f"revoked+{user_id}@revoked.invalid"


def _is_disposable_demo(tenant: Tenant) -> bool:
    return tenant.billing_tier == "demo" and tenant.domain.endswith(".demo.invalid")


async def _substantive_counts(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in _SUBSTANTIVE_TABLES:
        table = Base.metadata.tables.get(name)
        if table is None or "tenant_id" not in table.columns:
            continue
        total = await db.scalar(
            select(func.count())
            .select_from(table)
            .where(table.c.tenant_id == tenant_id)
        )
        if total:
            counts[name] = int(total)
    return counts


async def revoke_trial_tenant(
    db: AsyncSession,
    tenant: Tenant,
    *,
    confirm_email: str,
    actor_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Release a trial tenant's login addresses and revoke its provider grant.

    The caller must already have entered this tenant's RLS context and is
    responsible for committing and for recording the operator audit entry.
    """

    if _is_disposable_demo(tenant):
        raise TrialRevocationRefused(
            "Disposable demo workspaces are terminated from the demo panel"
        )

    config = await db.scalar(
        select(TenantSettings.custom_config).where(
            TenantSettings.tenant_id == tenant.id
        )
    )
    on_trial = config_marks_trial(config) or tenant.billing_tier in _TRIAL_TIERS
    already_revoked = tenant.is_active is False and tenant.expires_at is not None
    if not on_trial and not already_revoked:
        raise TrialRevocationRefused(
            "Tenant is not an active trial or an already-revoked trial"
        )

    substantive = await _substantive_counts(db, tenant.id)
    if substantive:
        raise TrialRevocationRefused(
            "Tenant holds customer work product; revoke is refused: "
            + ", ".join(f"{name}={count}" for name, count in sorted(substantive.items()))
        )

    users = list(
        (
            await db.scalars(
                select(User).where(
                    User.tenant_id == tenant.id,
                    User.principal_type == "human",
                )
            )
        ).all()
    )
    if not users:
        raise TrialRevocationRefused("Tenant has no human login to release")

    normalized = confirm_email.strip().lower()
    if normalized not in {user.email.strip().lower() for user in users}:
        raise TrialRevocationRefused(
            "confirmation email does not match any login in this tenant"
        )

    now = datetime.now(timezone.utc)
    released: list[str] = []
    for user in users:
        original = user.email
        user.email = _tombstone_email(user.id)
        user.is_active = False
        user.license_active = False
        user.premium_ai_enabled = False
        user.oauth_subject = None
        user.password_hash = None
        user.workspace_mcp_enabled = False
        user.sessions_valid_after = now
        user.updated_at = now
        released.append(original)

    credentials = await db.execute(
        delete(TenantCredential).where(TenantCredential.tenant_id == tenant.id)
    )

    tenant.is_active = False
    if tenant.expires_at is None or tenant.expires_at > now:
        tenant.expires_at = now

    settings_row = await db.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant.id)
    )
    if settings_row is None:
        settings_row = TenantSettings(tenant_id=tenant.id)
        db.add(settings_row)
    updated_config = dict(settings_row.custom_config or {})
    updated_config[TRIAL_MARKER] = False
    updated_config["revoked_at"] = now.isoformat()
    if reason:
        updated_config["revoked_reason"] = reason[:300]
    if actor_id:
        updated_config["revoked_by"] = actor_id
    settings_row.custom_config = updated_config

    await db.flush()

    return {
        "tenant_id": str(tenant.id),
        "released_emails": sorted(address.lower() for address in released),
        "users_revoked": len(users),
        "credentials_revoked": int(credentials.rowcount or 0),
    }
