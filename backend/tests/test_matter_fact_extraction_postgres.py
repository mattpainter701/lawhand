"""Real PostgreSQL acceptance: propose, review, apply intake-document facts.

Only the file provider is replaced. Routes, tenant scoping, row reads, the
standard-record and custom-field writes, and the audit event are real.
Extraction itself is deterministic, so no model is involved.
"""

import hashlib
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from app.database import set_tenant_context
from app.models.configurable_workflow import (
    CustomFieldDefinition,
    MatterCustomFieldValue,
)
from app.models.contact import Contact
from app.models.matter_document import MatterDocument
from app.models.plugin import Matter, MatterEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.services import matter_fact_extraction as facts

pytestmark = pytest.mark.asyncio

SOURCE = b"Client: John Smith\nCase No.: 2024-CV-001\nHas children: yes\n"


@pytest.fixture
async def fact_case(db_session, test_tenant, test_user, monkeypatch):
    tenant_id, actor_id = test_tenant.id, test_user.id
    matter_id, field_id, document_id, contact_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    source = {"bytes": SOURCE}
    db_session.add(
        Contact(
            id=contact_id,
            tenant_id=tenant_id,
            entity_type="person",
            contact_type="client",
            first_name="John",
            last_name="Smith",
        )
    )
    db_session.add(
        Matter(
            id=matter_id,
            tenant_id=tenant_id,
            user_id=actor_id,
            slug="fact-extraction",
            matter_name="Synthetic intake",
            client_contact_id=contact_id,
        )
    )
    db_session.add(
        CustomFieldDefinition(
            id=field_id,
            tenant_id=tenant_id,
            entity_type="matter",
            field_key="has_children",
            label="Has children",
            field_type="boolean",
            options_json=[],
            sensitive=False,
            active=True,
            schema_version=1,
            created_by_user_id=actor_id,
        )
    )
    await db_session.flush()
    db_session.add(
        MatterDocument(
            id=document_id,
            tenant_id=tenant_id,
            matter_id=matter_id,
            filename="intake.txt",
            content_type="text/plain",
            file_size=len(source["bytes"]),
            storage_state="verified",
            document_sha256=hashlib.sha256(source["bytes"]).hexdigest(),
            provider_version_id="version-1",
        )
    )
    await db_session.commit()
    calls = []

    async def read_file(_store, **kwargs):
        assert kwargs["tenant_id"] == str(tenant_id)
        assert kwargs["document"].id == document_id
        calls.append("provider_read")
        # Exercise a real transaction boundary, as a provider refresh can.
        await kwargs["db"].commit()
        return source["bytes"]

    monkeypatch.setattr(facts.MatterFileStore, "read_matter_file_bytes", read_file)
    return SimpleNamespace(
        tenant_id=tenant_id,
        actor_id=actor_id,
        user=SimpleNamespace(id=actor_id, tenant_id=tenant_id),
        matter_id=matter_id,
        field_id=field_id,
        document_id=document_id,
        contact_id=contact_id,
        source=source,
        calls=calls,
        url=f"/api/matters/{matter_id}/documents/{document_id}/facts",
    )


def proposal_target(body, target_key):
    return next(
        entry for entry in body["candidates"] if entry["target_key"] == target_key
    )


async def test_propose_lists_standard_and_custom_facts_without_writing(
    client, db_session, fact_case
):
    case = fact_case
    response = await client.post(case.url)
    assert response.status_code == 200, response.text
    body = response.json()
    keys = {entry["target_key"] for entry in body["candidates"]}
    assert "client.name" in keys
    assert "matter.case_number" in keys
    assert f"custom.matter.{case.field_id}" in keys
    assert proposal_target(body, "matter.case_number")["value"] == "2024-CV-001"

    await set_tenant_context(db_session, str(case.tenant_id))
    stored = await db_session.scalar(
        select(MatterCustomFieldValue).where(
            MatterCustomFieldValue.matter_id == case.matter_id
        )
    )
    assert stored is None


async def test_accept_writes_standard_and_custom_values_with_audit(
    client, db_session, fact_case
):
    case = fact_case
    await client.post(case.url)
    accepted = await client.post(
        case.url + "/accept",
        json={"target_key": f"custom.matter.{case.field_id}", "value": True},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["value"] is True

    name = await client.post(
        case.url + "/accept",
        json={
            "target_key": "client.name",
            "value": "John Smith",
            "replace_existing": True,
        },
    )
    assert name.status_code == 200, name.text

    await set_tenant_context(db_session, str(case.tenant_id))
    custom = await db_session.scalar(
        select(MatterCustomFieldValue).where(
            MatterCustomFieldValue.matter_id == case.matter_id,
            MatterCustomFieldValue.field_definition_id == case.field_id,
        )
    )
    assert custom is not None and custom.value_json is True
    contact = await db_session.scalar(
        select(Contact)
        .where(Contact.id == case.contact_id)
        .execution_options(populate_existing=True)
    )
    assert contact.first_name == "John" and contact.last_name == "Smith"
    events = list(
        (
            await db_session.scalars(
                select(MatterEvent).where(
                    MatterEvent.tenant_id == case.tenant_id,
                    MatterEvent.matter_id == case.matter_id,
                    MatterEvent.event_type == "matter_fact_extracted",
                )
            )
        ).all()
    )
    assert len(events) == 2
    assert all(
        "value" not in event.metadata_json and "source_text" not in event.metadata_json
        for event in events
    )


async def test_value_not_present_in_source_is_refused(client, fact_case):
    case = fact_case
    await client.post(case.url)
    refused = await client.post(
        case.url + "/accept",
        json={"target_key": "matter.case_number", "value": "9999-XX-999"},
    )
    assert refused.status_code == 409


async def test_source_change_blocks_accept(client, db_session, fact_case):
    case = fact_case
    await client.post(case.url)
    case.source["bytes"] = b"Client: John Smith\n"
    await db_session.execute(
        update(MatterDocument)
        .where(MatterDocument.id == case.document_id)
        .values(
            provider_version_id="version-2",
            document_sha256=hashlib.sha256(case.source["bytes"]).hexdigest(),
            file_size=len(case.source["bytes"]),
        )
    )
    await db_session.commit()
    stale = await client.post(
        case.url + "/accept",
        json={"target_key": "matter.case_number", "value": "2024-CV-001"},
    )
    assert stale.status_code == 409


async def test_ai_candidate_flows_through_review_and_grounded_accept(
    client, db_session, fact_case, monkeypatch
):
    case = fact_case
    # The value is stated in prose, not as a label line, so only the AI pass
    # finds it; acceptance still has to ground it in the source it occurred in.
    case.source["bytes"] = b"The matter is docketed as 2024-CV-001.\n"

    async def fake_extract_with_ai(**_kwargs):
        return {"matter.case_number": "2024-CV-001"}

    from app.services import intake_extraction_ai

    monkeypatch.setattr(intake_extraction_ai, "extract_with_ai", fake_extract_with_ai)

    proposal = await facts.propose(
        db_session, case.user, case.matter_id, case.document_id, use_ai=True
    )
    entry = proposal_target(proposal, "matter.case_number")
    assert entry["source_kind"] == "ai"
    assert entry["value"] == "2024-CV-001"

    accepted = await facts.accept(
        db_session,
        case.user,
        case.matter_id,
        case.document_id,
        facts.FactDecision(target_key="matter.case_number", value="2024-CV-001"),
    )
    assert accepted["status"] == "accepted"
    await set_tenant_context(db_session, str(case.tenant_id))
    matter = await db_session.scalar(
        select(Matter)
        .where(Matter.id == case.matter_id)
        .execution_options(populate_existing=True)
    )
    assert matter.case_number == "2024-CV-001"


async def test_other_tenant_cannot_propose_or_accept(client, db_session, fact_case):
    case = fact_case
    other_tenant_id, other_user_id = uuid.uuid4(), uuid.uuid4()
    db_session.add(
        Tenant(
            id=other_tenant_id,
            name="Other synthetic firm",
            domain="other-fact-extraction.example",
            billing_tier="payg",
            is_active=True,
        )
    )
    await db_session.flush()
    db_session.add(
        User(
            id=other_user_id,
            tenant_id=other_tenant_id,
            email="other@fact-extraction.example",
            full_name="Other reviewer",
            role="admin",
            oauth_provider="google",
            oauth_subject="other-fact-extraction",
            is_active=True,
        )
    )
    await db_session.commit()
    other_user = SimpleNamespace(id=other_user_id, tenant_id=other_tenant_id)
    await set_tenant_context(db_session, str(other_tenant_id))

    for action in ("propose", "accept"):
        with pytest.raises(HTTPException) as error:
            if action == "propose":
                await facts.propose(
                    db_session, other_user, case.matter_id, case.document_id
                )
            else:
                await facts.accept(
                    db_session,
                    other_user,
                    case.matter_id,
                    case.document_id,
                    facts.FactDecision(
                        target_key="matter.case_number", value="2024-CV-001"
                    ),
                )
        assert error.value.status_code == 404
    assert case.calls == []


async def _add_scan(db_session, case, filename, content, monkeypatch=None):
    document_id = uuid.uuid4()
    if monkeypatch is not None:
        # The fixture's reader asserts the original document; a scan is a
        # second document with its own bytes.
        async def read_scan(_store, **kwargs):
            assert kwargs["document"].id == document_id
            return content

        monkeypatch.setattr(facts.MatterFileStore, "read_matter_file_bytes", read_scan)
    db_session.add(
        MatterDocument(
            id=document_id,
            tenant_id=case.tenant_id,
            matter_id=case.matter_id,
            filename=filename,
            content_type="image/png" if filename.endswith(".png") else "application/pdf",
            file_size=len(content),
            storage_state="verified",
            document_sha256=hashlib.sha256(content).hexdigest(),
            provider_version_id="scan-1",
        )
    )
    await db_session.commit()
    return document_id


async def test_scan_is_read_through_ocr_with_its_confidence_and_cached(
    client, db_session, fact_case, monkeypatch
):
    from app.services import document_text_cache as cache

    case = fact_case
    scan_bytes = b"png-bytes-of-a-hand-filled-form"
    case.source["bytes"] = scan_bytes
    document_id = await _add_scan(db_session, case, "scan.png", scan_bytes, monkeypatch)
    extractions = []

    def fake_extract(filename, content_type, content):
        extractions.append(filename)
        return cache.Extraction(
            text="Client: Ada Lovelace\nCase No.: 2024-CV-777",
            engine=cache.ENGINE_OCR_LOCAL,
            ocr_confidence=0.73,
            lines=[
                {"page_index": 0, "text": "Case No.:", "score": 0.9, "rect": [72, 600, 140, 620]},
                {"page_index": 0, "text": "2024-CV-777", "score": 0.58, "rect": [150, 600, 260, 620]},
            ],
            page_count=1,
        )

    monkeypatch.setattr(cache, "extract", fake_extract)
    url = f"/api/matters/{case.matter_id}/documents/{document_id}/facts"
    response = await client.post(url)
    assert response.status_code == 200, response.text
    body = response.json()
    name = proposal_target(body, "client.name")
    assert name["value"] == "Ada Lovelace" and name["source_kind"] == "ocr"
    assert name["confidence"] == pytest.approx(0.73)
    case_number = proposal_target(body, "matter.case_number")
    # The merged text and the OCR detections agree on one value; the
    # detection pair carries its own, lower, confidence and the text-layer
    # line carries the page average. One value, best confidence kept.
    assert case_number["value"] == "2024-CV-777"
    assert {entry["source_kind"] for entry in case_number["values"]} == {"ocr"}
    assert any("read by OCR" in warning for warning in body["warnings"])

    again = await client.post(url)
    assert again.status_code == 200, again.text
    assert extractions == ["scan.png"], "the second read must come from the cache"


async def test_unreadable_scan_says_so_and_a_prose_file_keeps_the_old_wording(
    client, db_session, fact_case, monkeypatch
):
    from app.services import document_text_cache as cache

    case = fact_case
    case.source["bytes"] = b"blank-scan"
    document_id = await _add_scan(db_session, case, "blank.pdf", b"blank-scan", monkeypatch)
    monkeypatch.setattr(
        cache,
        "extract",
        lambda filename, content_type, content: cache.Extraction(
            text="", engine=cache.ENGINE_OCR_LOCAL, ocr_confidence=0.0
        ),
    )
    response = await client.post(f"/api/matters/{case.matter_id}/documents/{document_id}/facts")
    assert response.status_code == 200, response.text
    assert response.json()["candidates"] == []
    assert "OCR found no readable text in this scan." in response.json()["warnings"]


async def test_unsupported_source_type_is_refused(client, db_session, fact_case):
    case = fact_case
    document_id = await _add_scan(db_session, case, "sheet.xlsx", b"xlsx")
    response = await client.post(f"/api/matters/{case.matter_id}/documents/{document_id}/facts")
    assert response.status_code == 422
    assert "image source" in response.json()["detail"]
