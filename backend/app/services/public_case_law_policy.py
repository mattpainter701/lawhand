"""Firm policy on public case law, and how it narrows a conversation's choice.

The admin Case Law setting (``include_public_case_law``) has always been
written by the admin UI and never read by the chat path, so a firm that turned
public retrieval off still got CourtListener results. This module is the single
reader, and it defines the precedence: the firm setting can only *narrow* a
conversation's stored preference, never widen it. A conversation that asked for
public case law in a firm that forbids it runs without it and says so; a
conversation that asked to stay private is private regardless of firm policy.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import TenantSettings


async def tenant_public_case_law_allowed(db: AsyncSession, tenant_id) -> bool:
    """Whether this firm permits public case law in assistant retrieval.

    Absent or malformed configuration means allowed: public authority has been
    on by default since before the setting existed, and silently disabling
    retrieval on a config read error would change answers without telling
    anyone.
    """

    config = await db.scalar(
        select(TenantSettings.custom_config).where(
            TenantSettings.tenant_id == tenant_id
        )
    )
    if not isinstance(config, dict):
        return True
    return config.get("include_public_case_law") is not False


async def resolve_include_public(db: AsyncSession, tenant_id, requested: bool) -> bool:
    """Apply firm policy to a requested public-case-law preference."""

    if not requested:
        return False
    return await tenant_public_case_law_allowed(db, tenant_id)
