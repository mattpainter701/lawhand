"""Reading a matter's scanned form against the template that printed it."""

import hashlib
import uuid

import pytest
from sqlalchemy import select

from app.models.matter_document import MatterDocument
from app.models.plugin import MatterEvent
from app.services import matter_fact_extraction as facts
from app.services import template_form_reading as reading
from tests.test_document_templates import _fillable_pdf, _prepare_active_pdf_generation

pytestmark = pytest.mark.asyncio


async def _scan_document(db_session, *, tenant_id, matter_id, filename, content):
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
            document_sha256=hashlib.sha256(content).hexdigest(),
            provider_version_id="scan-1",
        )
    )
    await db_session.commit()
    return document_id


async def test_scan_is_read_field_by_field_against_the_generating_form(
    client, db_session, test_tenant, test_user, tmp_path, monkeypatch
):
    template_id, matter, _values, _preview = await _prepare_active_pdf_generation(
        client=client,
        db_session=db_session,
        test_tenant=test_tenant,
        test_user=test_user,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        slug="form-reading",
    )
    # The matter generated this form once; the scan is the same page, filled by hand.
    db_session.add(
        MatterEvent(
            tenant_id=test_tenant.id,
            matter_id=matter.id,
            event_type="document_generated",
            title="Generated document: form-reading.pdf",
            content="Generated from template form-reading form.",
            note_type="system",
            created_by=test_user.id,
            metadata_json={
                "template_id": template_id,
                "template_title": "form-reading form",
                "template_version_no": 1,
                "output_format": "pdf",
                "output_filename": "form-reading.pdf",
            },
        )
    )
    await db_session.commit()
    scan = _fillable_pdf()
    document_id = await _scan_document(
        db_session, tenant_id=test_tenant.id, matter_id=matter.id, filename="signed-scan.pdf", content=scan
    )

    async def read_file(_store, **kwargs):
        assert kwargs["document"].id == document_id
        return scan

    monkeypatch.setattr(facts.MatterFileStore, "read_matter_file_bytes", read_file)
    crops = []

    def fake_ocr(png: bytes):
        crops.append(len(png))
        # The first window of the form is the client's name; the rest are
        # left blank by the client.
        return ("Ada Lovelace", 0.66) if len(crops) == 1 else ("", 0.0)

    monkeypatch.setattr(reading, "_default_ocr", fake_ocr)

    sources = await client.get(
        f"/api/matters/{matter.id}/documents/{document_id}/facts/form-sources"
    )
    assert sources.status_code == 200, sources.text
    assert sources.json()["sources"][0]["template_id"] == template_id
    assert sources.json()["sources"][0]["version_no"] == 1

    read = await client.post(
        f"/api/matters/{matter.id}/documents/{document_id}/facts/from-form",
        json={"template_id": template_id},
    )
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["template_id"] == template_id and body["alignment"] == "scaled"
    template_row = await client.get(f"/api/templates/{template_id}")
    assert body["template_version_no"] == template_row.json()["published_version_no"]
    assert len(crops) == len(body["readings"]) == 3
    name = next(entry for entry in body["candidates"] if entry["target_key"] == "client.name")
    assert name["value"] == "Ada Lovelace"
    assert name["source_kind"] == "ocr_field" and name["source_locator"] == "field:client_name"
    assert name["confidence"] == pytest.approx(0.66)
    assert name["thumbnail_png_b64"]
    assert name["review_required"] is True
    first, *rest = body["readings"]
    assert first["name"] == "client_name" and first["target_key"] == "client.name"
    assert all(item["text"] == "" and item["target_key"] is None for item in rest)
    assert any("2 field(s) could not be read" in warning for warning in body["warnings"])

    # Nothing was written: the matter's client is untouched and the reading
    # is accepted only through the existing accept path.
    stored = await db_session.scalar(select(MatterDocument).where(MatterDocument.id == document_id))
    assert stored.generation_summary is None

    other_version = await client.post(
        f"/api/matters/{matter.id}/documents/{document_id}/facts/from-form",
        json={"template_id": template_id, "version_no": 9},
    )
    assert other_version.status_code == 404
    missing_template = await client.post(
        f"/api/matters/{matter.id}/documents/{document_id}/facts/from-form",
        json={"template_id": str(uuid.uuid4())},
    )
    assert missing_template.status_code == 404
    foreign_document = await client.post(
        f"/api/matters/{matter.id}/documents/{uuid.uuid4()}/facts/from-form",
        json={"template_id": template_id},
    )
    assert foreign_document.status_code == 404


async def test_form_sources_is_empty_for_a_matter_that_generated_nothing(
    client, db_session, test_tenant, test_user
):
    from app.models.plugin import Matter

    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug="no-forms",
        matter_name="No forms",
        matter_type="general",
    )
    db_session.add(matter)
    await db_session.commit()
    document_id = await _scan_document(
        db_session, tenant_id=test_tenant.id, matter_id=matter.id, filename="scan.pdf", content=b"%PDF-1.4"
    )
    sources = await client.get(f"/api/matters/{matter.id}/documents/{document_id}/facts/form-sources")
    assert sources.status_code == 200 and sources.json() == {"sources": []}
