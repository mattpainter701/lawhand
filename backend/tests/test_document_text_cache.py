"""The extraction cache: one read per digest, OCR where the text layer is missing."""

import hashlib
import uuid
from io import BytesIO

import pytest
from sqlalchemy import select

from app.database import set_tenant_context
from app.models.document_text_extraction import DocumentTextExtraction
from app.services import document_text_cache as cache
from app.services.template_ocr import OcrLine, PdfOcrResult, TemplateOcrError
from tests.esign_pdf_fixtures import acroform_pdf


def _blank_pdf() -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _ocr_result(text="Client name: Ada Lovelace", score=0.82) -> PdfOcrResult:
    line = OcrLine(
        page_index=0, text=text, score=score, rect=(72.0, 690.0, 350.0, 710.0)
    )
    return PdfOcrResult(
        text=text,
        lines=(line,),
        pages_analyzed=1,
        pages_total=1,
        average_confidence=score,
        truncated=False,
    )


def test_extract_reads_a_text_layer_without_ocr(monkeypatch):
    monkeypatch.setattr(
        cache, "_ocr_pdf", lambda content: pytest.fail("OCR must not run")
    )
    extraction = cache.extract("notes.txt", "text/plain", b"Client: Ada\n")
    assert extraction.engine == cache.ENGINE_TEXT_LAYER
    assert extraction.text == "Client: Ada\n" and not extraction.used_ocr
    pdf = cache.extract("form.pdf", "application/pdf", acroform_pdf())
    assert pdf.engine == cache.ENGINE_TEXT_LAYER and "Client name" in pdf.text
    assert pdf.page_count == 1


def test_extract_falls_back_to_ocr_for_a_page_with_no_text(monkeypatch):
    monkeypatch.setattr(cache, "_ocr_pdf", lambda content: _ocr_result())
    extraction = cache.extract("scan.pdf", "application/pdf", _blank_pdf())
    assert extraction.engine == cache.ENGINE_OCR_LOCAL and extraction.used_ocr
    assert "Ada Lovelace" in extraction.text
    assert extraction.ocr_confidence == pytest.approx(0.82)
    assert extraction.lines[0]["score"] == pytest.approx(0.82)
    assert extraction.lines[0]["page_index"] == 0


def test_extract_reports_an_unavailable_engine_and_keeps_the_text_layer(monkeypatch):
    def unavailable(content):
        raise TemplateOcrError(cache.OCR_UNAVAILABLE)

    monkeypatch.setattr(cache, "_ocr_pdf", unavailable)
    extraction = cache.extract("scan.pdf", "application/pdf", _blank_pdf())
    assert extraction.engine == cache.ENGINE_TEXT_LAYER
    assert extraction.warnings == [cache.OCR_UNAVAILABLE]
    assert extraction.text == ""


def test_extract_rasterises_an_image_before_ocr(monkeypatch):
    from PIL import Image

    seen = {}

    def fake_ocr(content):
        seen["pdf"] = content
        return _ocr_result("Case number: 2024-CV-9", 0.6)

    monkeypatch.setattr(cache, "_ocr_pdf", fake_ocr)
    buffer = BytesIO()
    Image.new("RGB", (300, 200), "white").save(buffer, format="PNG")
    extraction = cache.extract("scan.png", "image/png", buffer.getvalue())
    assert seen["pdf"].startswith(b"%PDF")
    assert extraction.used_ocr and "2024-CV-9" in extraction.text
    assert cache.is_image_filename("a.JPG") and not cache.is_image_filename("a.pdf")


@pytest.mark.asyncio
async def test_get_or_extract_reads_once_per_digest_and_tenant(
    db_session, test_tenant, monkeypatch
):
    calls = []

    def fake_extract(filename, content_type, content):
        calls.append(filename)
        return cache.Extraction(
            text="Client: Ada", engine=cache.ENGINE_TEXT_LAYER, page_count=1
        )

    monkeypatch.setattr(cache, "extract", fake_extract)
    await set_tenant_context(db_session, str(test_tenant.id))
    first = await cache.get_or_extract(
        db_session,
        tenant_id=test_tenant.id,
        content=b"same bytes",
        filename="a.txt",
        content_type="text/plain",
    )
    second = await cache.get_or_extract(
        db_session,
        tenant_id=test_tenant.id,
        content=b"same bytes",
        filename="renamed.txt",
        content_type="text/plain",
    )
    assert calls == ["a.txt"]
    assert not first.cached and second.cached and second.text == "Client: Ada"
    digest = hashlib.sha256(b"same bytes").hexdigest()
    row = await db_session.scalar(
        select(DocumentTextExtraction).where(
            DocumentTextExtraction.document_sha256 == digest
        )
    )
    assert row is not None and row.engine_version == cache.ENGINE_VERSION
    # Another tenant's lookup of the same digest sees nothing; the key is
    # tenant plus digest, never the digest alone.
    assert (
        await cache.lookup(db_session, tenant_id=uuid.uuid4(), document_sha256=digest)
        is None
    )
    # Different bytes miss by construction.
    await cache.get_or_extract(
        db_session,
        tenant_id=test_tenant.id,
        content=b"other bytes",
        filename="b.txt",
        content_type="text/plain",
    )
    assert calls == ["a.txt", "b.txt"]


@pytest.mark.asyncio
async def test_the_cache_row_is_committed_without_committing_the_caller(
    db_session, test_engine, test_tenant, monkeypatch
):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setattr(
        cache,
        "extract",
        lambda filename, content_type, content: cache.Extraction(
            text="Client: Ada", engine=cache.ENGINE_TEXT_LAYER, page_count=1
        ),
    )
    await set_tenant_context(db_session, str(test_tenant.id))
    tenant_id = test_tenant.id
    digest = hashlib.sha256(b"own unit").hexdigest()
    await cache.get_or_extract(
        db_session,
        tenant_id=tenant_id,
        content=b"own unit",
        filename="a.txt",
        content_type="text/plain",
    )
    # The caller's transaction is still open and untouched...
    assert db_session.in_transaction()
    # ...while another session already sees the committed row.
    other = async_sessionmaker(test_engine, expire_on_commit=False)
    async with other() as peer:
        await set_tenant_context(peer, str(tenant_id))
        assert (
            await cache.lookup(peer, tenant_id=tenant_id, document_sha256=digest)
        ) is not None
    # Rolling the caller back does not lose the cache.
    await db_session.rollback()
    await set_tenant_context(db_session, str(tenant_id))
    assert (
        await cache.lookup(db_session, tenant_id=tenant_id, document_sha256=digest)
    ) is not None


@pytest.mark.asyncio
async def test_a_cache_write_fault_still_returns_the_extraction(
    db_session, test_tenant, monkeypatch
):
    """The cache write runs on its own pooled connection. Exhausting the pool,
    or any transient database fault, costs the cache row — never the read."""

    from sqlalchemy.exc import SQLAlchemyError

    monkeypatch.setattr(
        cache,
        "extract",
        lambda filename, content_type, content: cache.Extraction(
            text="Client: Ada", engine=cache.ENGINE_TEXT_LAYER, page_count=1
        ),
    )

    def _exhausted():
        raise SQLAlchemyError("connection pool exhausted")

    monkeypatch.setattr(cache, "session_factory", _exhausted)
    await set_tenant_context(db_session, str(test_tenant.id))
    extraction = await cache.get_or_extract(
        db_session,
        tenant_id=test_tenant.id,
        content=b"unwritable bytes",
        filename="a.txt",
        content_type="text/plain",
    )
    assert extraction.text == "Client: Ada"
    assert not extraction.cached


@pytest.mark.asyncio
async def test_forget_if_unreferenced_keeps_shared_bytes_and_other_tenants(
    db_session, test_tenant, test_user
):
    from app.models.matter_document import MatterDocument
    from app.models.plugin import Matter

    tenant_id = test_tenant.id
    matter = Matter(
        id=uuid.uuid4(), tenant_id=tenant_id, user_id=test_user.id,
        slug=f"cache-{uuid.uuid4()}", matter_name="Cache", stage="New",
    )
    db_session.add(matter)
    await db_session.flush()
    digest = hashlib.sha256(b"shared").hexdigest()
    ids = []
    for name in ("a.txt", "b.txt"):
        document = MatterDocument(
            id=uuid.uuid4(), tenant_id=tenant_id, matter_id=matter.id,
            filename=name, content_type="text/plain", file_size=6,
            storage_state="verified", document_sha256=digest,
            provider_version_id="v1",
        )
        db_session.add(document)
        ids.append(document.id)
    from app.models.tenant import Tenant

    other = Tenant(name="Other firm", domain=f"other-{uuid.uuid4().hex[:8]}.example")
    db_session.add(other)
    await db_session.flush()
    other_tenant = other.id
    for tenant in (tenant_id, other_tenant):
        db_session.add(
            DocumentTextExtraction(
                tenant_id=tenant, document_sha256=digest, engine=cache.ENGINE_TEXT_LAYER,
                engine_version=cache.ENGINE_VERSION, text="shared",
            )
        )
    await db_session.flush()

    # One holder remains: nothing is dropped.
    assert await cache.forget_if_unreferenced(
        db_session, tenant_id=tenant_id, document_sha256=digest, except_document_id=ids[0]
    ) == 0
    await db_session.delete(await db_session.get(MatterDocument, ids[0]))
    await db_session.flush()
    # The last holder goes: this tenant's row goes, the other tenant's stays.
    assert await cache.forget_if_unreferenced(
        db_session, tenant_id=tenant_id, document_sha256=digest, except_document_id=ids[1]
    ) == 1
    remaining = (
        await db_session.execute(
            select(DocumentTextExtraction.tenant_id).where(
                DocumentTextExtraction.document_sha256 == digest
            )
        )
    ).scalars().all()
    assert remaining == [other_tenant]
    assert await cache.forget_if_unreferenced(
        db_session, tenant_id=tenant_id, document_sha256=None, except_document_id=ids[1]
    ) == 0


def test_migration_197_isolates_the_cache_by_tenant():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "197_document_evidence.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "196_mcp_usage_idempotency"' in source
    assert (
        "ENABLE ROW LEVEL SECURITY" in source and "FORCE ROW LEVEL SECURITY" in source
    )
    assert "document_text_extractions_tenant_isolation" in source
    assert "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid" in source
    assert "generation_summary" in source
