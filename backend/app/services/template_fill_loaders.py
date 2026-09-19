"""Database loaders for the Smart Fill engine.

Each loader reads one record the resolver needs, scoped to the tenant. They are
kept apart from the engine so a caller can supply in-memory stand-ins (the
tests and the quirk campaign do) and so the engine itself never issues a query.
A missing or malformed matter raises :class:`MatterLookupError`; the router
turns that into the HTTP status the route always returned.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.matter_party import MatterParty
from app.models.plugin import Matter
from app.models.retainer import Retainer


class MatterLookupError(LookupError):
    """The matter id is malformed (422) or not visible to the tenant (404)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def load_matter_context(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    matter_id: str | None,
) -> Matter | None:
    if not matter_id:
        return None
    try:
        parsed_matter_id = uuid.UUID(matter_id)
    except ValueError as exc:
        raise MatterLookupError(422, "Invalid matter_id") from exc

    result = await db.execute(
        select(Matter)
        .options(
            selectinload(Matter.client),
            selectinload(Matter.attorney_of_record),
        )
        .where(
            Matter.id == parsed_matter_id,
            Matter.tenant_id == tenant_id,
        )
    )
    matter = result.scalar_one_or_none()
    if not matter:
        raise MatterLookupError(404, "Matter not found")
    return matter


async def load_matter_parties(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    matter: Matter | None,
) -> list[MatterParty]:
    if matter is None:
        return []
    result = await db.execute(
        select(MatterParty)
        .where(
            MatterParty.matter_id == matter.id,
            MatterParty.tenant_id == tenant_id,
        )
        .order_by(
            MatterParty.is_primary.desc(),
            MatterParty.created_at,
            MatterParty.id,
        )
    )
    return list(result.scalars().all())


async def load_estate_for_matter(*, db: AsyncSession, tenant_id: uuid.UUID, matter):
    """The newest estate record linked to the matter, with its parties loaded."""

    from app.models.plugin import Estate

    return await db.scalar(
        select(Estate)
        .options(
            selectinload(Estate.fiduciaries),
            selectinload(Estate.beneficiaries),
            selectinload(Estate.assets),
            selectinload(Estate.liabilities),
        )
        .where(
            Estate.tenant_id == tenant_id,
            Estate.matter_id == matter.id,
            Estate.is_deleted.is_(False),
        )
        .order_by(Estate.created_at.desc())
        .limit(1)
    )


async def load_current_retainer(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    matter: Matter | None,
) -> Retainer | None:
    """Return the matter's current retainer, if it has one.

    "Current" is the most recently created *active* retainer; a matter can hold
    several retainer rows over its life (replenishments, refunds), and the
    replenishment threshold a template fills is the active agreement's, not a
    sum across history. When no active row exists, fall back to the most
    recently created row of any status so a retired retainer's terms do not
    silently fill from nothing.
    """

    if matter is None:
        return None
    return await db.scalar(
        select(Retainer)
        .where(
            Retainer.matter_id == matter.id,
            Retainer.tenant_id == tenant_id,
        )
        .order_by(
            case((Retainer.status == "active", 0), else_=1),
            Retainer.created_at.desc(),
        )
        .limit(1)
    )


Loader = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class Loaders:
    """The four reads the engine may perform, replaceable as a unit."""

    matter: Loader = load_matter_context
    parties: Loader = load_matter_parties
    estate: Loader = load_estate_for_matter
    retainer: Loader = load_current_retainer


DEFAULT_LOADERS = Loaders()
