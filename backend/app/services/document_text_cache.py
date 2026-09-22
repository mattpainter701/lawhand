"""What a matter document's bytes say, read once and remembered per tenant.

Every reader of a matter document (a fact proposal, the accept that re-proves
its source, the assistant's document text tool) used to download and parse the
file again, and none of them could read a scan at all: the OCR engine behind
template uploads was never reachable from a matter. This module is the one
place a document's text comes from. It reads the text layer, falls back to OCR
when a PDF page has none (the same heuristic template intake uses), normalises
an image upload to a PDF first, and remembers the result in
``document_text_extractions`` keyed by the tenant and the SHA-256 of the bytes.

The cache row is evidence about the document: which engine produced the text,
at what confidence, and whether it was cut short. Nothing here writes to a
matter or client field; proposals still go through a person.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.database import async_session_maker, set_tenant_context
from app.models.document_text_extraction import DocumentTextExtraction
from app.models.matter_document import MatterDocument
from app.utils.text_processing import extract_text

logger = logging.getLogger(__name__)

#: Bump when the extraction rules change so old rows are recomputed rather
#: than trusted.
ENGINE_VERSION = "1"
MAX_TEXT = 200_000
MAX_PDF_PAGES = 100
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff")

ENGINE_TEXT_LAYER = "text_layer"
ENGINE_OCR_LOCAL = "ocr_local"
ENGINE_OCR_AZURE = "ocr_azure"
ENGINE_MIXED = "mixed"

OCR_UNAVAILABLE = (
    "OCR is unavailable in this environment; only the text layer was read."
)


@dataclass
class Extraction:
    text: str
    engine: str
    lines: list[dict] = field(default_factory=list)
    ocr_confidence: float | None = None
    page_count: int | None = None
    truncated: bool = False
    cached: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def used_ocr(self) -> bool:
        return self.engine in {ENGINE_OCR_LOCAL, ENGINE_OCR_AZURE, ENGINE_MIXED}


def is_image_filename(filename: str) -> bool:
    return str(filename or "").lower().endswith(IMAGE_SUFFIXES)


def _ocr_engine_name() -> str:
    from app.config import get_settings

    provider = str(getattr(get_settings(), "TEMPLATE_OCR_PROVIDER", "") or "")
    return ENGINE_OCR_AZURE if provider.strip().lower() == "azure" else ENGINE_OCR_LOCAL


def _line_dicts(ocr_result) -> list[dict]:
    lines = []
    for line in getattr(ocr_result, "lines", ()) or ():
        lines.append(
            {
                "page_index": int(line.page_index),
                "text": str(line.text),
                "score": round(float(line.score), 4),
                "rect": [round(float(value), 2) for value in line.rect],
            }
        )
    return lines


def _ocr_pdf(content: bytes):
    """Run the OCR engine, or raise ``TemplateOcrError`` when it cannot run."""

    from app.services.template_ocr import TemplateOcrError, ocr_pdf

    try:
        return ocr_pdf(content)
    except TemplateOcrError:
        raise
    except ImportError as exc:  # pragma: no cover - depends on the runtime
        raise TemplateOcrError(OCR_UNAVAILABLE) from exc


def _extract_pdf(content: bytes) -> Extraction:
    import io

    from pypdf import PdfReader

    from app.services.template_intake import (
        _extract_pdf_page_text,
        _merge_pdf_text_and_ocr,
    )
    from app.services.template_ocr import TemplateOcrError

    reader = PdfReader(io.BytesIO(content))
    page_count = len(reader.pages)
    text, page_text, sparse_pages = _extract_pdf_page_text(
        reader, max_pages=MAX_PDF_PAGES, max_chars=MAX_TEXT
    )
    truncated = page_count > MAX_PDF_PAGES or len(text) >= MAX_TEXT
    if not sparse_pages:
        return Extraction(
            text=text,
            engine=ENGINE_TEXT_LAYER,
            page_count=page_count,
            truncated=truncated,
        )
    try:
        ocr_result = _ocr_pdf(content)
    except TemplateOcrError as exc:
        warning = (
            str(exc)
            if str(exc) == OCR_UNAVAILABLE
            else (
                f"OCR could not read this document ({exc}); only the text layer was read."
            )
        )
        return Extraction(
            text=text,
            engine=ENGINE_TEXT_LAYER,
            page_count=page_count,
            truncated=truncated,
            warnings=[warning],
        )
    merged = _merge_pdf_text_and_ocr(page_text, ocr_result, max_chars=MAX_TEXT)
    all_sparse = len(sparse_pages) >= min(page_count, MAX_PDF_PAGES)
    return Extraction(
        text=merged,
        engine=_ocr_engine_name() if all_sparse else ENGINE_MIXED,
        lines=_line_dicts(ocr_result),
        ocr_confidence=float(getattr(ocr_result, "average_confidence", 0.0) or 0.0),
        page_count=page_count,
        truncated=truncated or bool(getattr(ocr_result, "truncated", False)),
    )


def extract(filename: str, content_type: str, content: bytes) -> Extraction:
    """Read a document's text, with OCR where the text layer is missing.

    Synchronous and safe to run in a worker thread. Raises ``ValueError`` /
    ``RuntimeError`` for a document that cannot be read at all, as
    ``extract_text`` does; an OCR failure is a warning, never an error, because
    the text layer (possibly empty) is still an honest answer.
    """

    name = str(filename or "").lower()
    if is_image_filename(name):
        from app.services.template_ocr import TemplateOcrError, image_to_pdf

        try:
            normalized = image_to_pdf(content)
        except TemplateOcrError as exc:
            raise ValueError(str(exc)) from exc
        extraction = _extract_pdf(normalized.content)
        if extraction.engine == ENGINE_TEXT_LAYER and not extraction.text.strip():
            extraction.engine = ENGINE_TEXT_LAYER
        return extraction
    if name.endswith(".pdf") or str(content_type or "").lower() == "application/pdf":
        return _extract_pdf(content)
    text = extract_text(content, content_type or "", filename)
    return Extraction(
        text=text[:MAX_TEXT],
        engine=ENGINE_TEXT_LAYER,
        truncated=len(text) > MAX_TEXT,
    )


def _from_row(row: DocumentTextExtraction) -> Extraction:
    return Extraction(
        text=row.text,
        engine=row.engine,
        lines=list(row.lines_json or []),
        ocr_confidence=row.ocr_confidence,
        page_count=row.page_count,
        truncated=bool(row.truncated),
        cached=True,
    )


async def lookup(db, *, tenant_id, document_sha256: str) -> Extraction | None:
    row = await db.scalar(
        select(DocumentTextExtraction).where(
            DocumentTextExtraction.tenant_id == uuid.UUID(str(tenant_id)),
            DocumentTextExtraction.document_sha256 == document_sha256,
            DocumentTextExtraction.engine_version == ENGINE_VERSION,
        )
    )
    return _from_row(row) if row is not None else None


#: The session the cache row is written through. Derived data gets its own
#: unit of work so the caller's transaction never commits, and never has to
#: re-apply its transaction-scoped tenant context, on account of a cache
#: write. A module attribute so tests bind it to their engine.
session_factory = async_session_maker


async def get_or_extract(
    db,
    *,
    tenant_id,
    content: bytes,
    filename: str,
    content_type: str | None,
) -> Extraction:
    """Serve the document's text from the cache, extracting and storing on a miss.

    The row is written and committed through ``session_factory`` so the next
    reader (a different request, the durable job, the assistant) finds it
    while ``db`` stays exactly as the caller left it: nothing committed, no
    tenant context to restore. Two readers racing on the same digest both
    extract; the second insert loses and re-reads the winner.
    """

    tenant = uuid.UUID(str(tenant_id))
    digest = hashlib.sha256(content).hexdigest()
    cached = await lookup(db, tenant_id=tenant, document_sha256=digest)
    if cached is not None:
        return cached
    extraction = await asyncio.to_thread(extract, filename, content_type or "", content)
    row = DocumentTextExtraction(
        tenant_id=tenant,
        document_sha256=digest,
        engine=extraction.engine,
        engine_version=ENGINE_VERSION,
        text=extraction.text,
        lines_json=extraction.lines or None,
        page_count=extraction.page_count,
        ocr_confidence=extraction.ocr_confidence,
        truncated=extraction.truncated,
    )
    try:
        async with session_factory() as own:
            await set_tenant_context(own, str(tenant))
            own.add(row)
            await own.commit()
    except IntegrityError:
        logger.info("document text extraction raced for %s; reusing the winner", digest)
        winner = await lookup(db, tenant_id=tenant, document_sha256=digest)
        if winner is not None:
            winner.warnings = list(extraction.warnings)
            return winner
    return extraction


async def forget_if_unreferenced(
    db, *, tenant_id, document_sha256: str | None, except_document_id
) -> int:
    """Drop the tenant's cache rows for ``document_sha256`` once no document carries it.

    Called from a document delete, in the caller's transaction, with the
    deleted document excluded: the row is the document's text, and it lives
    exactly as long as some document of the tenant has those bytes. Returns
    the number of rows removed.
    """

    if not document_sha256:
        return 0
    tenant = uuid.UUID(str(tenant_id))
    still_held = await db.scalar(
        select(func.count(MatterDocument.id)).where(
            MatterDocument.tenant_id == tenant,
            MatterDocument.document_sha256 == document_sha256,
            MatterDocument.id != except_document_id,
        )
    )
    if still_held:
        return 0
    result = await db.execute(
        delete(DocumentTextExtraction).where(
            DocumentTextExtraction.tenant_id == tenant,
            DocumentTextExtraction.document_sha256 == document_sha256,
        )
    )
    return int(result.rowcount or 0)
