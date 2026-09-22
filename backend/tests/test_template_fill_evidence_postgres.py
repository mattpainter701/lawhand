"""Document evidence: from the extraction cache into Smart Fill, lowest precedence."""

import hashlib
import uuid

import pytest

from app.database import set_tenant_context
from app.models.contact import Contact
from app.models.document_text_extraction import DocumentTextExtraction
from app.models.matter_document import MatterDocument
from app.models.plugin import Matter
from app.services import document_prefill, document_text_cache as cache
from app.services import template_fill_engine as engine
from app.services.template_fill_loaders import (
    MAX_EVIDENCE_DOCUMENTS,
    Loaders,
    load_document_evidence,
    memoized,
)

pytestmark = pytest.mark.asyncio


async def _matter(db_session, tenant_id, user_id, *, email=None):
    contact_id, matter_id = uuid.uuid4(), uuid.uuid4()
    db_session.add(
        Contact(
            id=contact_id,
            tenant_id=tenant_id,
            entity_type="person",
            contact_type="client",
            first_name="Ada",
            last_name="Lovelace",
            email=email,
        )
    )
    db_session.add(
        Matter(
            id=matter_id,
            tenant_id=tenant_id,
            user_id=user_id,
            slug=f"evidence-{matter_id.hex[:8]}",
            matter_name="Evidence matter",
            client_contact_id=contact_id,
        )
    )
    await db_session.commit()
    return await db_session.get(Matter, matter_id)


async def _scan(db_session, tenant_id, matter_id, *, filename, text, category=None, confidence=0.7):
    content = f"{filename}:{text}".encode()
    digest = hashlib.sha256(content).hexdigest()
    document_id = uuid.uuid4()
    db_session.add(
        MatterDocument(
            id=document_id,
            tenant_id=tenant_id,
            matter_id=matter_id,
            filename=filename,
            content_type="application/pdf",
            file_size=len(content),
            storage_state="verified",
            document_sha256=digest,
            document_category=category,
        )
    )
    db_session.add(
        DocumentTextExtraction(
            tenant_id=tenant_id,
            document_sha256=digest,
            engine=cache.ENGINE_OCR_LOCAL,
            engine_version=cache.ENGINE_VERSION,
            text=text,
            ocr_confidence=confidence,
        )
    )
    await db_session.commit()
    return document_id


async def test_evidence_fills_a_blank_but_never_a_record_value(
    db_session, test_tenant, test_user
):
    matter = await _matter(db_session, test_tenant.id, test_user.id, email=None)
    await set_tenant_context(db_session, str(test_tenant.id))
    scan_id = await _scan(
        db_session, test_tenant.id, matter.id,
        filename="intake-scan.pdf",
        text="Client name: Not Ada\nEmail: ada@example.test\nCase No.: 2026-CV-7",
    )
    evidence = await load_document_evidence(db=db_session, tenant_id=test_tenant.id, matter=matter)
    by_alias = {item.alias: item for item in evidence}
    assert "client_email" in by_alias, (evidence,)
    assert by_alias["client_email"].value == "ada@example.test"
    assert by_alias["client_email"].document_id == scan_id
    assert by_alias["client_email"].source_kind == "ocr"
    assert by_alias["case_number"].value == "2026-CV-7"

    template = type("T", (), {})()
    template.id = uuid.uuid4()
    template.body = "{{client_name}} {{client_email}} {{case_number}}"
    template.variable_schema = {"fields": [
        {"name": "client_name"}, {"name": "client_email"}, {"name": "case_number"},
    ]}
    await db_session.refresh(matter, attribute_names=["client"])
    prepared = await engine.prepare_fill(
        db_session, template=template, tenant_id=test_tenant.id, matter=matter, actor=None
    )
    by_variable = prepared.by_variable
    # The contact's own name wins; the scan's "Not Ada" is a recorded loss.
    # (A bare "Client:" line would match nothing: it names no field.)
    assert by_variable["client_name"].suggested_value == "Ada Lovelace"
    assert by_variable["client_name"].source_type == "contact"
    assert any(c.alias == "client_name" and any(loss["source_type"] == "document_evidence" for loss in c.losers) for c in prepared.collisions)
    # The blank email is filled from the scan, capped and marked for review.
    email = by_variable["client_email"]
    assert email.suggested_value == "ada@example.test"
    assert email.source_type == "document_evidence"
    assert email.review_required is True
    assert email.confidence == pytest.approx(0.7)
    assert email.provenance["source_document_id"] == str(scan_id)
    assert email.provenance["source_filename"] == "intake-scan.pdf"
    assert "document_evidence" in prepared.sources_loaded


async def test_generated_documents_other_tenants_and_conflicts_are_not_evidence(
    db_session, test_tenant, test_user
):
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    await set_tenant_context(db_session, str(test_tenant.id))
    await _scan(db_session, test_tenant.id, matter.id, filename="fee.pdf", text="Email: generated@example.test", category="generated")
    # Two different answers in one scan: a conflict for the facts review, not evidence.
    await _scan(db_session, test_tenant.id, matter.id, filename="two.pdf", text="Email: one@example.test\nEmail: two@example.test")
    evidence = await load_document_evidence(db=db_session, tenant_id=test_tenant.id, matter=matter)
    assert evidence == ()
    # Another tenant's lookup sees none of this matter's documents.
    assert await load_document_evidence(db=db_session, tenant_id=uuid.uuid4(), matter=matter) == ()


async def test_newest_document_wins_ties_and_the_digest_moves_with_a_new_scan(
    db_session, test_tenant, test_user
):
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    await set_tenant_context(db_session, str(test_tenant.id))
    await db_session.refresh(matter, attribute_names=["client"])
    before = await document_prefill.matter_facts_digest(db_session, matter)
    await _scan(db_session, test_tenant.id, matter.id, filename="old.pdf", text="Email: old@example.test", confidence=0.7)
    after_first = await document_prefill.matter_facts_digest(db_session, matter)
    assert after_first != before
    await _scan(db_session, test_tenant.id, matter.id, filename="new.pdf", text="Email: new@example.test", confidence=0.7)
    evidence = await load_document_evidence(db=db_session, tenant_id=test_tenant.id, matter=matter)
    assert [item.value for item in evidence if item.alias == "client_email"] == ["new@example.test"]
    assert await document_prefill.matter_facts_digest(db_session, matter) != after_first
    assert MAX_EVIDENCE_DOCUMENTS >= 10


async def test_memoized_loaders_read_each_family_once(db_session, test_tenant, test_user):
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    calls = []

    async def counting(**kwargs):
        calls.append(kwargs["matter"].id)
        return ()

    loaders = memoized(Loaders(parties=counting, estate=counting, retainer=counting, document_evidence=counting))
    for _ in range(3):
        await loaders.parties(db=db_session, tenant_id=test_tenant.id, matter=matter)
        await loaders.document_evidence(db=db_session, tenant_id=test_tenant.id, matter=matter)
    assert len(calls) == 2
