"""Role and licensing access helpers."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.tenant import get_current_user

ADMIN_ROLE = "admin"
ACCOUNTANT_ROLE = "accountant"
STANDARD_ROLES = {"user", ACCOUNTANT_ROLE, ADMIN_ROLE}
FINANCE_ROLES = {ADMIN_ROLE, ACCOUNTANT_ROLE}
CLIENT_ROLE = "client"


def normalize_role(role: str | None) -> str:
    value = (role or "user").strip().lower()
    return value if value in STANDARD_ROLES else "user"


def is_client_portal_user(user) -> bool:
    """True for a client-portal login (``User.role == "client"``)."""
    return (getattr(user, "role", "") or "").strip().lower() == CLIENT_ROLE


def require_firm_staff(
    user, message: str = "Only firm staff can use matter documents."
) -> None:
    """Refuse client-portal logins on a staff route.

    A client-portal login is a real ``User`` whose token ``get_current_user``
    accepts, so a client could replay it against the staff API. Call this right
    after ``get_current_user`` and before any database or provider work. Client
    access belongs under ``/api/portal/...``.
    """
    if is_client_portal_user(user):
        raise HTTPException(
            status_code=403,
            detail={"code": "staff_only", "message": message},
        )


async def require_firm_staff_user(user=Depends(get_current_user)):
    """Router dependency: the signed-in user, refused if a client-portal login.

    Put it on a staff router's ``dependencies`` so every route refuses a
    client before its body runs, including routes added later. It shares the
    request's cached ``get_current_user`` result with handlers that declare it.
    """
    require_firm_staff(user, "Only firm staff can use the matters API.")
    return user


def can_manage_finance(role: str | None) -> bool:
    return normalize_role(role) in FINANCE_ROLES


async def require_finance_admin(request: Request, db: AsyncSession = Depends(get_db)):
    """Allow tenant admins and accountants into billing/licensing surfaces."""
    from app.services.rbac_service import get_user_capabilities

    user = await get_current_user(request, db)
    caps = await get_user_capabilities(db, user.id)
    if "view_billing" in caps or "manage_billing" in caps:
        return user
    if can_manage_finance(user.role):  # legacy fallback
        return user
    raise HTTPException(status_code=403, detail="Finance access required")


def require_capability(capability: str):
    """Dependency factory: 403 unless the user holds `capability` via any role."""

    async def _dep(request: Request, db: AsyncSession = Depends(get_db)):
        from app.services.rbac_service import get_user_capabilities

        user = await get_current_user(request, db)
        caps = await get_user_capabilities(db, user.id)
        if capability not in caps:
            raise HTTPException(
                status_code=403, detail=f"Missing capability: {capability}"
            )
        return user

    return _dep


def require_capabilities(*required: str):
    """Require every named capability for a compound privileged operation."""

    async def _dep(request: Request, db: AsyncSession = Depends(get_db)):
        from app.services.rbac_service import get_user_capabilities

        user = await get_current_user(request, db)
        caps = await get_user_capabilities(db, user.id)
        missing = sorted(set(required) - caps)
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Missing capabilities: {', '.join(missing)}",
            )
        return user

    return _dep


def require_any_capability(*allowed: str):
    """Allow a read/review surface to either authors or legal approvers."""

    async def _dep(request: Request, db: AsyncSession = Depends(get_db)):
        from app.services.rbac_service import get_user_capabilities

        user = await get_current_user(request, db)
        caps = await get_user_capabilities(db, user.id)
        if not set(allowed) & caps:
            raise HTTPException(
                status_code=403,
                detail=f"Missing one of capabilities: {', '.join(sorted(allowed))}",
            )
        return user

    return _dep
