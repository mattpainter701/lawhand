"""A matter-scoped index over the cached text of its documents (Phase 5e).

``document_text_cache`` keeps each document's text per tenant and digest.
This module turns that text into ``matter_document_chunks`` rows, one matter
and one document at a time, and answers "what do this matter's documents say
about X" over them: full-text always, by meaning too when the firm has an
embedding provider.

What it is not: a matter record, a Smart Fill source, or a firm-wide memory.
A result is a pointer to an excerpt of one document a person can open. The
index is derived data keyed by the document's digest and the extraction
engine version, so changed bytes re-index and a deleted document drops its
rows (``ON DELETE CASCADE``). Indexing is a convenience on the extraction
path and never a gate: a failure is logged, the extraction stands.

Chunks are cut by characters, on paragraph and sentence breaks, rather than
by the token counter in ``app.utils.text_processing.chunk_text``: that
counter needs a downloaded encoding, and this index must build wherever the
extraction cache does, offline included.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import delete, func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import set_tenant_context
from app.models.matter_document import MatterDocument
from app.models.matter_document_chunk import MatterDocumentChunk
from app.services.document_text_cache import ENGINE_VERSION

logger = logging.getLogger(__name__)

#: Characters per chunk and the overlap carried into the next one. About 400
#: tokens of English, the same order as the firm-memory chunks.
CHUNK_CHARS = 1_800
OVERLAP_CHARS = 200
#: One document contributes at most this many chunks; the extraction cache
#: caps text at 200,000 characters, so this bounds a run-away scan.
MAX_CHUNKS = 400
MAX_QUERY_CHARS = 200
SNIPPET_CHARS = 280
#: Reciprocal-rank fusion constant: the usual 60 keeps a top full-text hit
#: and a top semantic hit on equal footing.
RRF_K = 60
#: Relevance floor for the semantic branch, as a cosine distance (1 - cosine
#: similarity). A query with no real match otherwise returns its nearest chunks
#: regardless of distance and presents them as answers. 0.6 keeps moderately
#: related passages and drops near-orthogonal noise; the word branch answers on
#: its own, so this only trims the meaning hits. Tunable per embedding model.
MAX_COSINE_DISTANCE = 0.6

_BREAK = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def split_text(
    text: str, *, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS
) -> list[str]:
    """Cut ``text`` into pieces of about ``size`` characters on natural breaks.

    Pieces overlap by roughly ``overlap`` characters so a sentence that
    straddles a boundary is searchable from either side. Deterministic and
    dependency-free.
    """

    clean = re.sub(r"[ \t]+", " ", str(text or "")).strip()
    if not clean:
        return []
    if len(clean) <= size:
        return [clean]
    sentences = [part.strip() for part in _BREAK.split(clean) if part and part.strip()]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        # A single run longer than a chunk is cut hard so no piece exceeds
        # the size by more than one sentence.
        while len(sentence) > size:
            head, sentence = sentence[:size], sentence[size - overlap :]
            if current:
                pieces.append(current)
                current = ""
            pieces.append(head)
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= size:
            current = f"{current} {sentence}"
        else:
            pieces.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail} {sentence}".strip() if tail else sentence
    if current:
        pieces.append(current)
    return pieces


def default_embedder():
    """The firm's embedding service when one is configured, else ``None``.

    Constructed lazily so environments without a provider (tests, a firm on
    full-text only) never build a client.
    """

    settings = get_settings()
    configured = bool(settings.OPENAI_API_KEY) or bool(
        getattr(settings, "LITELLM_ENABLED", False)
        and getattr(settings, "LITELLM_EMBEDDING_MODEL", "")
    )
    if not configured:
        return None
    try:
        from app.services.embeddings import EmbeddingService

        return EmbeddingService()
    except Exception:  # pragma: no cover - a provider fault must not block indexing
        logger.warning("Embedding service unavailable; indexing by words only")
        return None


async def index_document(
    db: AsyncSession,
    *,
    tenant_id,
    document: MatterDocument,
    extraction,
    embedder=None,
) -> int:
    """Index ``extraction.text`` for ``document``; returns the chunk count.

    Idempotent per (document, digest, engine version): rows already present
    for these bytes are kept as they are. Rows for other bytes of the same
    document are replaced. Commits, like the cache write it follows, and
    restores the tenant context.
    """

    tenant_uuid = uuid.UUID(str(tenant_id))
    text = str(getattr(extraction, "text", "") or "")
    if not document.matter_id or not document.document_sha256 or not text.strip():
        return 0
    existing = await db.scalar(
        select(func.count(MatterDocumentChunk.id)).where(
            MatterDocumentChunk.tenant_id == tenant_uuid,
            MatterDocumentChunk.matter_document_id == document.id,
            MatterDocumentChunk.document_sha256 == document.document_sha256,
            MatterDocumentChunk.engine_version == ENGINE_VERSION,
        )
    )
    if existing:
        return int(existing)
    pieces = split_text(text)[:MAX_CHUNKS]
    vectors: list[Any] = []
    if embedder is not None and pieces:
        try:
            vectors = list(await embedder.embed_batch(pieces))
        except Exception:  # noqa: BLE001 - words still index when meaning cannot
            logger.warning(
                "Embedding failed for document %s", document.id, exc_info=True
            )
            vectors = []
    if len(vectors) != len(pieces):
        vectors = [None] * len(pieces)
    # Snapshot before the delete: a flush can expire the row.
    document_id, matter_id, sha256 = (
        document.id,
        document.matter_id,
        document.document_sha256,
    )
    await db.execute(
        delete(MatterDocumentChunk).where(
            MatterDocumentChunk.tenant_id == tenant_uuid,
            MatterDocumentChunk.matter_document_id == document_id,
        )
    )
    for index, (piece, vector) in enumerate(zip(pieces, vectors)):
        db.add(
            MatterDocumentChunk(
                tenant_id=tenant_uuid,
                matter_id=matter_id,
                matter_document_id=document_id,
                document_sha256=sha256,
                engine_version=ENGINE_VERSION,
                chunk_index=index,
                content=piece,
                embedding=vector,
            )
        )
    await db.commit()
    await set_tenant_context(db, str(tenant_uuid))
    return len(pieces)


async def forget_document(db: AsyncSession, *, tenant_id, document_id) -> int:
    """Drop a document's rows explicitly; the cascade also does this on delete."""

    result = await db.execute(
        delete(MatterDocumentChunk).where(
            MatterDocumentChunk.tenant_id == uuid.UUID(str(tenant_id)),
            MatterDocumentChunk.matter_document_id == uuid.UUID(str(document_id)),
        )
    )
    return int(result.rowcount or 0)


async def indexed_documents(
    db: AsyncSession, *, tenant_id, matter_id
) -> dict[str, int]:
    """``document_id`` → chunk count for a matter, for a UI to say what is searchable."""

    rows = await db.execute(
        select(
            MatterDocumentChunk.matter_document_id,
            func.count(MatterDocumentChunk.id),
        )
        .where(
            MatterDocumentChunk.tenant_id == uuid.UUID(str(tenant_id)),
            MatterDocumentChunk.matter_id == uuid.UUID(str(matter_id)),
        )
        .group_by(MatterDocumentChunk.matter_document_id)
    )
    return {str(document_id): int(count) for document_id, count in rows.all()}


def _snippet(content: str) -> str:
    text = " ".join(str(content or "").split())
    return text if len(text) <= SNIPPET_CHARS else text[: SNIPPET_CHARS - 1] + "…"


async def search(
    db: AsyncSession,
    *,
    tenant_id,
    matter_id,
    query: str,
    limit: int = 8,
    embedder=None,
) -> list[dict[str, Any]]:
    """Excerpts from this matter's documents that answer ``query``.

    Full-text (``websearch_to_tsquery``) ranks by words; when an embedder
    yields a query vector and the matter has embedded chunks, the nearest
    chunks by cosine distance are fused in by reciprocal rank. Each hit is
    ``{document_id, filename, chunk_index, snippet, score, open_url}``. The
    snippet is the document's own text: untrusted source material.
    """

    tenant_uuid = uuid.UUID(str(tenant_id))
    matter_uuid = uuid.UUID(str(matter_id))
    clean = " ".join(str(query or "").split())[:MAX_QUERY_CHARS]
    if len(clean) < 2:
        return []
    limit = max(1, min(int(limit), 25))
    tsquery = func.websearch_to_tsquery("english", clean)
    scope = (
        MatterDocumentChunk.tenant_id == tenant_uuid,
        MatterDocumentChunk.matter_id == matter_uuid,
    )
    ranked: dict[tuple[uuid.UUID, int], dict[str, Any]] = {}

    def fuse(rows, kind: str) -> None:
        for rank, (chunk, filename, headline) in enumerate(rows, start=1):
            key = (chunk.matter_document_id, chunk.chunk_index)
            hit = ranked.setdefault(
                key,
                {
                    "document_id": str(chunk.matter_document_id),
                    "filename": filename,
                    "chunk_index": int(chunk.chunk_index),
                    "snippet": _snippet(headline or chunk.content),
                    "score": 0.0,
                    "matched_by": [],
                    "open_url": (
                        f"/api/matters/{matter_uuid}/documents/"
                        f"{chunk.matter_document_id}/open"
                    ),
                },
            )
            hit["score"] += 1.0 / (RRF_K + rank)
            hit["matched_by"].append(kind)
            if headline and kind == "words":
                hit["snippet"] = _snippet(headline)

    words = await db.execute(
        select(
            MatterDocumentChunk,
            MatterDocument.filename,
            func.ts_headline(
                "english",
                MatterDocumentChunk.content,
                tsquery,
                "MaxWords=45, MinWords=25, StartSel=**, StopSel=**",
            ),
        )
        .join(
            MatterDocument,
            (MatterDocument.id == MatterDocumentChunk.matter_document_id)
            & (MatterDocument.tenant_id == MatterDocumentChunk.tenant_id),
        )
        .where(*scope, MatterDocumentChunk.fts.op("@@")(tsquery))
        .order_by(func.ts_rank_cd(MatterDocumentChunk.fts, tsquery).desc())
        .limit(limit * 2)
    )
    fuse(words.all(), "words")

    vector = None
    if embedder is not None:
        try:
            vector = await embedder.embed_text(clean)
        except Exception:  # noqa: BLE001 - words alone still answer
            logger.warning("Query embedding failed", exc_info=True)
            vector = None
    if vector:
        nearest = await db.execute(
            select(MatterDocumentChunk, MatterDocument.filename, null())
            .join(
                MatterDocument,
                (MatterDocument.id == MatterDocumentChunk.matter_document_id)
                & (MatterDocument.tenant_id == MatterDocumentChunk.tenant_id),
            )
            .where(
                *scope,
                MatterDocumentChunk.embedding.isnot(None),
                MatterDocumentChunk.embedding.cosine_distance(vector)
                <= MAX_COSINE_DISTANCE,
            )
            .order_by(MatterDocumentChunk.embedding.cosine_distance(vector))
            .limit(limit * 2)
        )
        fuse(nearest.all(), "meaning")

    hits = sorted(
        ranked.values(),
        key=lambda item: (-item["score"], item["filename"], item["chunk_index"]),
    )
    return hits[:limit]
