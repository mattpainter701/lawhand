"""Database loaders for the Smart Fill engine.

Each loader reads one record the resolver needs, scoped to the tenant. They are
kept apart from the engine so a caller can supply in-memory stand-ins (the
tests and the quirk campaign do) and so the engine itself never issues a query.
A missing or malformed matter raises :class:`MatterLookupError`; the router
turns that into the HTTP status the route always returned.
"""

from __future__ import annotations

import dataclasses
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


@dataclass(frozen=True)
class DocumentEvidence:
    """One value a matter document supports, ready for the engine.

    ``alias`` is the Smart Fill alias the fact target resolves through, so
    the source can write it without knowing anything about bindings.
    """

    alias: str
    value: str
    confidence: float
    document_id: uuid.UUID
    filename: str
    source_kind: str
    source_locator: str
    document_sha256: str
    read_at: str | None = None


_BARE_ENTITY_KEYS = frozenset({"client", "matter", "contact"})

#: Newest documents read for evidence; a matter with a hundred scans gets
#: its most recent hundred, not a full-text pass over its whole history.
MAX_EVIDENCE_DOCUMENTS = 50


async def load_document_evidence(
    *, db: AsyncSession, tenant_id: uuid.UUID, matter
) -> tuple[DocumentEvidence, ...]:
    """Values the matter's own documents support, best per alias.

    Reads the extraction cache for the matter's verified documents (a scan's
    OCR text included) and runs the fact reader over each. Only standard
    fact targets become evidence: accepted custom-field values already reach
    the fill through the custom-field suggestions. Documents the platform
    generated are not evidence about the matter, so they are skipped.
    """

    from app.models.document_text_extraction import DocumentTextExtraction
    from app.models.matter_document import MatterDocument
    from app.services import document_text_cache, matter_fact_extraction as facts
    from app.services.template_cards import alias_for_path

    if matter is None or not hasattr(db, "execute"):
        # An in-memory stand-in (the tests, the quirk campaign) holds no
        # documents; only a session can read the cache.
        return ()
    documents = (
        (
            await db.execute(
                select(MatterDocument)
                .where(
                    MatterDocument.tenant_id == tenant_id,
                    MatterDocument.matter_id == matter.id,
                    MatterDocument.document_sha256.isnot(None),
                    MatterDocument.storage_state == "verified",
                )
                .order_by(MatterDocument.created_at.desc())
                .limit(MAX_EVIDENCE_DOCUMENTS * 2)
            )
        )
        .scalars()
        .all()
    )
    documents = [
        document
        for document in documents
        if str(document.document_category or "") != "generated"
    ][:MAX_EVIDENCE_DOCUMENTS]
    if not documents:
        return ()
    digests = {document.document_sha256 for document in documents}
    rows = (
        (
            await db.execute(
                select(DocumentTextExtraction).where(
                    DocumentTextExtraction.tenant_id == tenant_id,
                    DocumentTextExtraction.document_sha256.in_(digests),
                    DocumentTextExtraction.engine_version
                    == document_text_cache.ENGINE_VERSION,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return ()
    by_digest = {row.document_sha256: row for row in rows}
    # A bare entity word ("Client:", "Matter:") is a label the fact reader
    # accepts for every field of that entity, which makes one line a
    # conflicting answer for all of them. Evidence for a fill needs the
    # field named, so those tokens are dropped from the match keys here.
    targets = [
        dataclasses.replace(target, match_keys=target.match_keys - _BARE_ENTITY_KEYS)
        for target in await facts.build_targets(db, tenant_id)
        if target.kind == "standard"
    ]
    aliases = {target.key: alias_for_path(target.binding) for target in targets}
    best: dict[str, DocumentEvidence] = {}
    for document in documents:  # newest first
        row = by_digest.get(document.document_sha256)
        if row is None or not (row.text or "").strip():
            continue
        extraction = document_text_cache.Extraction(
            text=row.text,
            engine=row.engine,
            lines=list(row.lines_json or []),
            ocr_confidence=row.ocr_confidence,
            cached=True,
        )
        found = facts.extract_candidates(
            text=row.text, form_values=[], targets=targets, extraction=extraction
        )
        for target_key, candidates in found.items():
            alias = aliases.get(target_key)
            if not alias:
                continue
            distinct = facts._distinct(candidates)
            if len(distinct) != 1:
                # Two different values in one document is a conflict the
                # facts review shows; it is not evidence for a fill.
                continue
            candidate = distinct[0]
            current = best.get(alias)
            if current is not None and current.confidence >= candidate.confidence:
                continue
            best[alias] = DocumentEvidence(
                alias=alias,
                value=candidate.value,
                confidence=round(float(candidate.confidence), 4),
                document_id=document.id,
                filename=str(document.filename or ""),
                source_kind=candidate.source_kind,
                source_locator=candidate.source_locator,
                document_sha256=document.document_sha256,
                read_at=row.created_at.isoformat() if row.created_at else None,
            )
    return tuple(best[alias] for alias in sorted(best))


Loader = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class Loaders:
    """The reads the engine may perform, replaceable as a unit."""

    matter: Loader = load_matter_context
    parties: Loader = load_matter_parties
    estate: Loader = load_estate_for_matter
    retainer: Loader = load_current_retainer
    document_evidence: Loader = load_document_evidence


DEFAULT_LOADERS = Loaders()


def memoized(loaders: Loaders = DEFAULT_LOADERS) -> Loaders:
    """A bundle that reads each record once per matter and then remembers it.

    A job that fills twenty templates for one matter has no reason to read
    the parties twenty times. Keyed by matter id; the matter loader itself is
    not memoized because it is what produces the key.
    """

    cache: dict[tuple[str, str], Any] = {}

    def remember(name: str, loader: Loader) -> Loader:
        async def load(**kwargs):
            matter = kwargs.get("matter")
            key = (name, str(getattr(matter, "id", "") or ""))
            if key not in cache:
                cache[key] = await loader(**kwargs)
            return cache[key]

        return load

    return Loaders(
        matter=loaders.matter,
        parties=remember("parties", loaders.parties),
        estate=remember("estate", loaders.estate),
        retainer=remember("retainer", loaders.retainer),
        document_evidence=remember("document_evidence", loaders.document_evidence),
    )
