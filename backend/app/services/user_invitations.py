"""Staff invitations: hashed, expiring, single-use tokens.

An administrator invites a person by email. The person proves they received
that email by presenting the token, and only then may set a password or link a
Google/Microsoft identity. Only the sha256 of the token is stored.

The token is also how the tenant is discovered, so the lookup runs before any
tenant context exists. It uses the migration-192 SELECT policy that matches a
single presented hash, then binds the invitation's own tenant before reading
anything else. Nothing here uses the auth ``rls_bypass`` escape hatch.
"""

import hashlib
import secrets
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import set_invitation_token_lookup, set_tenant_context
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.services.tenant_state import require_active_tenant
from app.utils.auth_errors import AuthRefusal

INVITE_TTL = timedelta(days=7)
MAX_TOKEN_LENGTH = 128
ACCEPT_METHODS = frozenset({"password", "google", "microsoft"})

_REFUSALS: dict[str, tuple[int, str]] = {
    "invite_invalid": (
        400,
        "This invitation link is not valid. Ask your firm administrator to send a new one.",
    ),
    "invite_expired": (
        400,
        "This invitation has expired. Ask your firm administrator to resend it.",
    ),
    "invite_accepted": (
        400,
        "This invitation has already been used. Sign in instead.",
    ),
    "tenant_inactive": (
        403,
        "This firm's account is not active. Contact your firm administrator.",
    ),
    "account_active": (
        409,
        "This account is already active. Sign in instead.",
    ),
}


class InvitationRefusal(AuthRefusal):
    """A refused invitation lookup or acceptance with a user-safe code."""

    def __init__(self, code: str):
        status_code, detail = _REFUSALS[code]
        super().__init__(code=code, status_code=status_code, detail=detail)


@dataclass
class InvitationContext:
    invitation: UserInvitation
    user: User
    tenant: Tenant


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def hash_invite_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def invitation_url(raw_token: str) -> str:
    base = (get_settings().FRONTEND_URL or "http://localhost:3000").rstrip("/")
    return f"{base}/accept-invite?token={urllib.parse.quote(raw_token, safe='')}"


def mask_email(email: str) -> str:
    """Show enough of an address to recognise it without disclosing it."""
    local, _, domain = (email or "").partition("@")
    if not local or not domain:
        return "•••"
    return f"{local[0]}•••@{domain}"


async def create_invitation(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    now: datetime | None = None,
) -> str:
    """Issue a fresh invitation, revoking any still-open one. Returns the raw token.

    The caller must already have bound ``tenant_id`` as the tenant context.
    """
    now = now or _utcnow()
    await revoke_open_invitation(db, tenant_id=tenant_id, user_id=user_id, now=now)
    raw_token = secrets.token_urlsafe(32)
    db.add(
        UserInvitation(
            tenant_id=tenant_id,
            user_id=user_id,
            token_hash=hash_invite_token(raw_token),
            expires_at=now + INVITE_TTL,
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
    )
    await db.flush()
    return raw_token


async def revoke_open_invitation(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> bool:
    """Revoke the user's open invitation, if any. Returns whether one was open."""
    result = await db.execute(
        update(UserInvitation)
        .where(
            UserInvitation.tenant_id == tenant_id,
            UserInvitation.user_id == user_id,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=now or _utcnow())
        .execution_options(synchronize_session=False)
    )
    return (result.rowcount or 0) > 0


async def has_unaccepted_invitation(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """True when the user was invited and has never accepted any invitation."""
    rows = (
        (
            await db.execute(
                select(UserInvitation.accepted_at).where(
                    UserInvitation.tenant_id == tenant_id,
                    UserInvitation.user_id == user_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return bool(rows) and all(accepted_at is None for accepted_at in rows)


async def invitation_statuses(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    now: datetime | None = None,
) -> dict[uuid.UUID, tuple[str, datetime | None]]:
    """Map each invited-but-never-accepted user to ``(status, expires_at)``.

    ``pending`` and ``expired`` describe the open invitation. ``revoked`` means
    every invitation was revoked: the person is still only reachable through a
    new invitation, so the admin list must offer to resend rather than show a
    plain inactive account whose reactivation would be refused.
    """
    if not user_ids:
        return {}
    now = now or _utcnow()
    rows = (
        await db.execute(
            select(
                UserInvitation.user_id,
                UserInvitation.expires_at,
                UserInvitation.accepted_at,
                UserInvitation.revoked_at,
            ).where(
                UserInvitation.tenant_id == tenant_id,
                UserInvitation.user_id.in_(user_ids),
            )
        )
    ).all()

    accepted: set[uuid.UUID] = set()
    statuses: dict[uuid.UUID, tuple[str, datetime | None]] = {}
    for user_id, expires_at, accepted_at, revoked_at in rows:
        if accepted_at is not None:
            accepted.add(user_id)
        elif revoked_at is None:
            status = "expired" if _as_utc(expires_at) <= now else "pending"
            statuses[user_id] = (status, expires_at)
        else:
            statuses.setdefault(user_id, ("revoked", None))
    for user_id in accepted:
        statuses.pop(user_id, None)
    return statuses


async def resolve_invitation(
    db: AsyncSession, raw_token: str | None, *, now: datetime | None = None
) -> InvitationContext:
    """Find the invitation for a presented token and bind its tenant.

    Every refusal is raised before anything is written, so callers can run
    this as a pure pre-check.
    """
    if not raw_token or len(raw_token) > MAX_TOKEN_LENGTH:
        raise InvitationRefusal("invite_invalid")
    now = now or _utcnow()
    token_hash = hash_invite_token(raw_token)

    await set_invitation_token_lookup(db, token_hash)
    invitation = await db.scalar(
        select(UserInvitation).where(UserInvitation.token_hash == token_hash)
    )
    await set_invitation_token_lookup(db, None)
    if invitation is None:
        raise InvitationRefusal("invite_invalid")

    await set_tenant_context(db, str(invitation.tenant_id))
    if invitation.revoked_at is not None:
        raise InvitationRefusal("invite_invalid")
    if invitation.accepted_at is not None:
        raise InvitationRefusal("invite_accepted")
    if _as_utc(invitation.expires_at) <= now:
        raise InvitationRefusal("invite_expired")

    user = await db.scalar(
        select(User).where(
            User.id == invitation.user_id,
            User.tenant_id == invitation.tenant_id,
        )
    )
    tenant = await db.scalar(select(Tenant).where(Tenant.id == invitation.tenant_id))
    # Service principals never authenticate, so an invitation row pointing at
    # one is treated as if it did not exist.
    if user is None or tenant is None or user.principal_type != "human":
        raise InvitationRefusal("invite_invalid")
    try:
        require_active_tenant(tenant)
    except HTTPException as exc:
        raise InvitationRefusal("tenant_inactive") from exc
    if user.is_active:
        raise InvitationRefusal("account_active")
    return InvitationContext(invitation=invitation, user=user, tenant=tenant)


async def claim_invitation(
    db: AsyncSession,
    invitation_id: uuid.UUID,
    method: str,
    *,
    now: datetime | None = None,
) -> None:
    """Mark an invitation accepted, exactly once.

    The conditional update is the single-use guarantee: of two concurrent
    requests carrying the same token, only one matches the still-open row.
    """
    if method not in ACCEPT_METHODS:
        raise ValueError(f"unsupported invitation accept method: {method}")
    now = now or _utcnow()
    result = await db.execute(
        update(UserInvitation)
        .where(
            UserInvitation.id == invitation_id,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
            UserInvitation.expires_at > now,
        )
        .values(accepted_at=now, accepted_method=method)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise InvitationRefusal("invite_invalid")
