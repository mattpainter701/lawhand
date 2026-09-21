"""Phase 5e: the matter-scoped index over cached document text.

Real rows. Indexing follows the extraction cache (same text, same digest),
is idempotent per digest, replaces rows when the bytes change, and drops
them with the document. Search is scoped to one matter of one tenant, by
words always and by meaning when an embedder answers. The route and the
matter-context excerpts section read the same index.
"""

import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models.matter_document import MatterDocument
from app.models.matter_document_chunk import MatterDocumentChunk
from app.models.plugin import Matter
from app.schemas.chat_action import GetMatterContextArgs
from app.services import matter_document_index as index
from app.services import matter_workspace_capabilities as workspace
from app.services.automation_capabilities import CapabilityContext

pytestmark = pytest.mark.asyncio

HEARING = (
    "NOTICE OF HEARING. The motion to compel discovery responses is set for "
    "hearing on March 3, 2027 at 9:00 a.m. in Courtroom 4B before Judge Amari. "
    "Counsel shall appear in person."
)
RETAINER = (
    "ENGAGEMENT AGREEMENT. The client agrees to a retainer of $5,000 to be "
    "applied against hourly fees. Costs are billed monthly."
)


def _extraction(text):
    return SimpleNamespace(text=text, engine="text_layer")


async def _matter(db, tenant, user, name="Indexed matter"):
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"index-{uuid.uuid4()}",
        matter_name=name,
        stage="New",
    )
    db.add(matter)
    await db.commit()
    return matter


async def _document(db, *, tenant_id, matter_id, filename, content: bytes):
    document = MatterDocument(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        matter_id=matter_id,
        filename=filename,
        content_type="text/plain",
        file_size=len(content),
        storage_state="verified",
        document_sha256=hashlib.sha256(content).hexdigest(),
        provider_version_id="v1",
    )
    db.add(document)
    await db.commit()
    return document


class _Embedder:
    """A stand-in provider: a fixed direction per known phrase, zero otherwise."""

    def __init__(self, hot: str):
        self.hot = hot
        self.batches = 0

    def _vector(self, text):
        vector = [0.0] * 1536
        vector[0] = 1.0 if self.hot in text else 0.0
        vector[1] = 0.0 if self.hot in text else 1.0
        return vector

    async def embed_batch(self, texts):
        self.batches += 1
        return [self._vector(text) for text in texts]

    async def embed_text(self, text):
        return self._vector(text)


async def test_split_text_cuts_on_breaks_and_overlaps():
    assert index.split_text("") == []
    assert index.split_text("short") == ["short"]
    long = " ".join(f"Sentence number {n} ends here." for n in range(400))
    pieces = index.split_text(long, size=300, overlap=60)
    assert len(pieces) > 5
    assert all(len(piece) <= 300 + 40 for piece in pieces)
    # The overlap carries the tail of one piece into the head of the next.
    assert pieces[0][-30:].split()[-1] in pieces[1]
    assert "".join(pieces).count("Sentence number 399") >= 1


async def test_index_follows_the_digest_and_search_is_scoped(
    db_session, test_tenant, test_user
):
    tenant_id = test_tenant.id
    matter = await _matter(db_session, test_tenant, test_user)
    other = await _matter(db_session, test_tenant, test_user, name="Other matter")
    matter_id, other_id = matter.id, other.id
    notice = await _document(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        filename="notice.txt", content=HEARING.encode(),
    )
    agreement = await _document(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        filename="engagement.txt", content=RETAINER.encode(),
    )
    elsewhere = await _document(
        db_session, tenant_id=tenant_id, matter_id=other_id,
        filename="other-notice.txt", content=HEARING.encode(),
    )
    notice_id, agreement_id = notice.id, agreement.id

    assert await index.index_document(
        db_session, tenant_id=tenant_id, document=notice, extraction=_extraction(HEARING)
    ) == 1
    assert await index.index_document(
        db_session, tenant_id=tenant_id, document=agreement, extraction=_extraction(RETAINER)
    ) == 1
    assert await index.index_document(
        db_session, tenant_id=tenant_id, document=elsewhere, extraction=_extraction(HEARING)
    ) == 1
    # Idempotent per digest: a second pass adds nothing.
    assert await index.index_document(
        db_session, tenant_id=tenant_id, document=notice, extraction=_extraction(HEARING)
    ) == 1
    assert await db_session.scalar(select(func.count(MatterDocumentChunk.id))) == 3
    # Empty text indexes nothing.
    blank = await _document(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        filename="blank.txt", content=b"   ",
    )
    assert await index.index_document(
        db_session, tenant_id=tenant_id, document=blank, extraction=_extraction("  ")
    ) == 0

    hits = await index.search(
        db_session, tenant_id=tenant_id, matter_id=matter_id, query="hearing courtroom"
    )
    assert [hit["document_id"] for hit in hits] == [str(notice_id)]
    assert "**hearing**" in hits[0]["snippet"] or "**Hearing**" in hits[0]["snippet"].replace("HEARING", "Hearing")
    assert hits[0]["matched_by"] == ["words"]
    assert hits[0]["open_url"] == f"/api/matters/{matter_id}/documents/{notice_id}/open"
    assert await index.search(
        db_session, tenant_id=tenant_id, matter_id=matter_id, query="retainer"
    ) and (await index.search(
        db_session, tenant_id=tenant_id, matter_id=matter_id, query="retainer"
    ))[0]["document_id"] == str(agreement_id)
    assert await index.search(
        db_session, tenant_id=tenant_id, matter_id=matter_id, query="zzqx"
    ) == []
    assert await index.search(
        db_session, tenant_id=tenant_id, matter_id=matter_id, query="h"
    ) == []
    assert await index.indexed_documents(
        db_session, tenant_id=tenant_id, matter_id=matter_id
    ) == {str(notice_id): 1, str(agreement_id): 1}

    # New bytes for the same document replace its rows.
    notice = await db_session.get(MatterDocument, notice_id)
    changed = HEARING.replace("March 3", "April 9")
    notice.document_sha256 = hashlib.sha256(changed.encode()).hexdigest()
    await db_session.commit()
    assert await index.index_document(
        db_session, tenant_id=tenant_id, document=notice, extraction=_extraction(changed)
    ) == 1
    rows = (
        await db_session.execute(
            select(MatterDocumentChunk).where(
                MatterDocumentChunk.matter_document_id == notice_id
            )
        )
    ).scalars().all()
    assert len(rows) == 1 and "April 9" in rows[0].content

    # Deleting the document drops its rows with it.
    notice = await db_session.get(MatterDocument, notice_id)
    await db_session.delete(notice)
    await db_session.commit()
    assert await db_session.scalar(
        select(func.count(MatterDocumentChunk.id)).where(
            MatterDocumentChunk.matter_document_id == notice_id
        )
    ) == 0
    assert await index.forget_document(
        db_session, tenant_id=tenant_id, document_id=agreement_id
    ) == 1


async def test_meaning_joins_words_when_an_embedder_answers(
    db_session, test_tenant, test_user
):
    tenant_id = test_tenant.id
    matter = await _matter(db_session, test_tenant, test_user)
    matter_id = matter.id
    notice = await _document(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        filename="notice.txt", content=HEARING.encode(),
    )
    agreement = await _document(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        filename="engagement.txt", content=RETAINER.encode(),
    )
    notice_id, agreement_id = notice.id, agreement.id
    embedder = _Embedder(hot="hearing")
    await index.index_document(
        db_session, tenant_id=tenant_id, document=notice,
        extraction=_extraction(HEARING), embedder=embedder,
    )
    await index.index_document(
        db_session, tenant_id=tenant_id, document=agreement,
        extraction=_extraction(RETAINER), embedder=embedder,
    )
    assert embedder.batches == 2

    # Words and meaning both point at the notice; the hit reports both.
    hits = await index.search(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        query="hearing March", embedder=embedder, limit=1,
    )
    assert hits and hits[0]["document_id"] == str(notice_id)
    assert set(hits[0]["matched_by"]) == {"words", "meaning"}
    only_meaning = await index.search(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        query="hearing", embedder=_Embedder(hot="retainer"), limit=2,
    )
    assert {hit["document_id"] for hit in only_meaning} == {str(notice_id), str(agreement_id)}
    meaning_hit = next(h for h in only_meaning if h["document_id"] == str(agreement_id))
    assert meaning_hit["matched_by"] == ["meaning"]

    # A provider fault indexes by words only and searches by words only.
    class _Broken:
        async def embed_batch(self, texts):
            raise RuntimeError("provider down")

        async def embed_text(self, text):
            raise RuntimeError("provider down")

    later = await _document(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        filename="later.txt", content=b"Costs are billed monthly.",
    )
    assert await index.index_document(
        db_session, tenant_id=tenant_id, document=later,
        extraction=_extraction("Costs are billed monthly."), embedder=_Broken(),
    ) == 1
    hits = await index.search(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        query="billed monthly", embedder=_Broken(),
    )
    assert {hit["document_id"] for hit in hits} >= {str(later.id)}


async def test_route_and_matter_context_read_the_index(
    client, db_session, test_tenant, test_user
):
    tenant_id = test_tenant.id
    matter = await _matter(db_session, test_tenant, test_user)
    matter_id = matter.id
    notice = await _document(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        filename="notice.txt", content=HEARING.encode(),
    )
    notice_id = notice.id
    await index.index_document(
        db_session, tenant_id=tenant_id, document=notice, extraction=_extraction(HEARING)
    )

    response = await client.get(
        f"/api/matters/{matter_id}/documents/search", params={"q": "compel"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["query"] == "compel" and body["indexed_documents"] == 1
    assert [hit["document_id"] for hit in body["results"]] == [str(notice_id)]
    assert "compel" in body["results"][0]["snippet"].lower()
    too_short = await client.get(
        f"/api/matters/{matter_id}/documents/search", params={"q": "c"}
    )
    assert too_short.status_code == 422
    missing = await client.get(
        f"/api/matters/{uuid.uuid4()}/documents/search", params={"q": "compel"}
    )
    assert missing.status_code == 404

    context = CapabilityContext(
        db=db_session,
        user=SimpleNamespace(id=test_user.id, tenant_id=tenant_id),
        granted_scopes=frozenset({"matters:read", "documents:read"}),
    )
    payload = await workspace.get_matter_context(
        context,
        GetMatterContextArgs(
            matter_id=matter_id, sections=["excerpts"], query="Judge Amari"
        ),
    )
    (excerpt,) = payload["excerpts"]
    assert excerpt["document_id"] == str(notice_id)
    assert "Amari" in excerpt["snippet"]
    assert excerpt["snippet"].startswith("<")  # fenced as untrusted text
    without_query = await workspace.get_matter_context(
        context, GetMatterContextArgs(matter_id=matter_id, sections=["excerpts"])
    )
    assert without_query["excerpts"] == []


async def test_extraction_queues_the_index_job_and_the_worker_builds_it(
    db_session, test_tenant, test_user, monkeypatch
):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.durable_job import DurableJob
    from app.services import durable_job_worker as worker
    from app.services import matter_fact_extraction as facts

    tenant_id = test_tenant.id
    matter = await _matter(db_session, test_tenant, test_user)
    document = await _document(
        db_session, tenant_id=tenant_id, matter_id=matter.id,
        filename="notice.txt", content=HEARING.encode(),
    )
    document_id, digest = document.id, document.document_sha256

    # Reading the document caches its text in its own unit of work and queues
    # one index job; the caller's transaction is not committed on its behalf.
    extraction = await facts._extract(db_session, tenant_id, document, HEARING.encode())
    assert "hearing" in extraction.text.lower()
    assert db_session.in_transaction()
    jobs = (
        await db_session.execute(
            select(DurableJob).where(DurableJob.kind == index.JOB_KIND)
        )
    ).scalars().all()
    assert len(jobs) == 1 and jobs[0].status == "pending"
    assert jobs[0].idempotency_key == index.job_key(document_id, digest)
    assert jobs[0].payload == {"document_id": str(document_id), "document_sha256": digest}
    # Nothing is indexed until the job runs.
    assert await db_session.scalar(select(func.count(MatterDocumentChunk.id))) == 0
    # A second read (a cache hit) queues nothing new.
    await facts._extract(db_session, tenant_id, document, HEARING.encode())
    assert await db_session.scalar(select(func.count(DurableJob.id))) == 1

    job_id = jobs[0].id
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    with patch.object(worker, "async_session_maker", factory):
        await worker.process_job(job_id, tenant_id)
    job = await db_session.get(DurableJob, job_id)
    await db_session.refresh(job)
    assert job.status == "completed"
    assert job.result == {"status": "indexed", "document_id": str(document_id), "chunks": 1}
    assert await db_session.scalar(
        select(func.count(MatterDocumentChunk.id)).where(
            MatterDocumentChunk.matter_document_id == document_id
        )
    ) == 1

    # Bytes that moved after queueing are skipped; the next read queues anew.
    document = await db_session.get(MatterDocument, document_id)
    changed = HEARING.replace("Amari", "Babbage")
    document.document_sha256 = hashlib.sha256(changed.encode()).hexdigest()
    job.status = "pending"
    await db_session.commit()
    with patch.object(worker, "async_session_maker", factory):
        await worker.process_job(job_id, tenant_id)
    await db_session.refresh(job)
    assert job.result == {"status": "skipped", "reason": "document bytes changed"}

    # A queue fault is logged, never raised into the read.
    document = await db_session.get(MatterDocument, document_id)

    class _Boom:
        def __call__(self):
            raise RuntimeError("factory down")

    monkeypatch.setattr(index, "session_factory", _Boom())
    assert await index.enqueue_index(
        tenant_id=tenant_id, document_id=document_id, document_sha256=digest
    ) is False
    extraction = await facts._extract(db_session, tenant_id, document, changed.encode())
    assert "Babbage" in extraction.text


async def test_deleting_the_last_document_with_those_bytes_drops_the_cache(
    client, db_session, test_tenant, test_user
):
    from app.models.document_text_extraction import DocumentTextExtraction
    from app.services import document_text_cache as cache

    tenant_id = test_tenant.id
    matter = await _matter(db_session, test_tenant, test_user)
    matter_id = matter.id
    first = await _document(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        filename="notice.txt", content=HEARING.encode(),
    )
    twin = await _document(
        db_session, tenant_id=tenant_id, matter_id=matter_id,
        filename="notice-copy.txt", content=HEARING.encode(),
    )
    first_id, twin_id, digest = first.id, twin.id, first.document_sha256
    await cache.get_or_extract(
        db_session, tenant_id=tenant_id, content=HEARING.encode(),
        filename="notice.txt", content_type="text/plain",
    )
    await index.index_document(
        db_session, tenant_id=tenant_id, document=first, extraction=_extraction(HEARING)
    )

    def rows():
        return db_session.scalar(
            select(func.count(DocumentTextExtraction.id)).where(
                DocumentTextExtraction.document_sha256 == digest
            )
        )

    assert await rows() == 1
    gone = await client.delete(f"/api/matters/{matter_id}/documents/{first_id}")
    assert gone.status_code in (200, 204), gone.text
    # The twin still carries the bytes, so the text stays; the chunks went with the row.
    assert await rows() == 1
    assert await db_session.scalar(
        select(func.count(MatterDocumentChunk.id)).where(
            MatterDocumentChunk.matter_document_id == first_id
        )
    ) == 0
    gone = await client.delete(f"/api/matters/{matter_id}/documents/{twin_id}")
    assert gone.status_code in (200, 204), gone.text
    assert await rows() == 0


async def test_migration_text_pins_rls_cascade_and_head():
    source = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "200_matter_document_index.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "199_workflow_document_requests"' in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "REFERENCES matter_documents (tenant_id, id) ON DELETE CASCADE" in source
    assert "USING gin (fts)" in source
    assert "vector(1536)" in source
