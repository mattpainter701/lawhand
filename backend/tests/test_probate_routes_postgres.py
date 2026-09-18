"""The Probate tab's routes: facts, determination, intake pull, clock, forms."""

import hashlib
import json
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.contact import Contact
from app.models.document_template import DocumentTemplate
from app.models.estate import EstateDeadline
from app.models.plugin import Estate, EstateEvent, Matter
from app.models.sample_template import SampleTemplate
from app.models.task import Task
from app.routers import document_templates
from app.schemas.matter_intake import IntakeStart
from app.services import matter_intake as intake_service
from app.services import intake_starter_pack
from app.services.probate import forms as forms_module

SEED_DIR = Path(__file__).resolve().parents[1] / "seed" / "sample_templates"
BASE = "/api/plugins/trust-estate"


@pytest.fixture(autouse=True)
async def _probate_staff_capability(db_session, test_tenant, test_user):
    """The staff workbench now requires ``manage_matters`` on every route."""

    from app.models.rbac import Role, UserRole

    role = Role(
        tenant_id=test_tenant.id,
        name="Probate staff",
        capabilities=["manage_matters"],
    )
    db_session.add(role)
    await db_session.flush()
    db_session.add(
        UserRole(
            user_id=test_user.id,
            role_id=role.id,
            tenant_id=test_tenant.id,
            source="manual",
        )
    )
    await db_session.commit()
    return role


async def _estate(client, **overrides) -> dict:
    payload = {"estate_name": "Estate of Ole Olson", "estate_type": "probate"}
    payload.update(overrides)
    response = await client.post(f"{BASE}/estates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


FACTS = {
    "decedent_name": "Ole Olson",
    "date_of_death": "01/15/2025",
    "date_of_birth": "1940-06-15",
    "domicile_state": "North Dakota",
    "domicile_county": "Cass",
    "real_property_in_nd": True,
    "probate_property_value": "$250,000",
    "will_exists": True,
    "will_original_available": True,
    "will_execution_date": "2010-05-06",
    "applicant_name": "Ann Olson",
    "applicant_relationship": "spouse",
    "applicant_is_nominee": True,
    "applicant_address": "1 Main St, Fargo, ND 58102",
    "applicant_phone": "701-555-0100",
    "heirs": [
        {
            "name": "Ann Olson",
            "age": "70",
            "relationship": "spouse",
            "address": "Fargo",
        },
        {"name": "Bob Olson", "age": "45", "relationship": "son"},
    ],
    "prior_appointment": False,
    "demand_for_notice": False,
    "probate_opened_elsewhere": False,
}


@pytest.mark.asyncio
async def test_saving_facts_determines_the_track_and_mirrors_the_opening_facts(
    client, db_session
):
    estate = await _estate(client)
    blank = await client.get(f"{BASE}/estates/{estate['id']}/probate")
    assert blank.status_code == 200, blank.text
    assert blank.json()["determination"] is None
    assert [row["number"] for row in blank.json()["forms"] if row["number"]] == list(
        range(1, 20)
    )

    saved = await client.put(f"{BASE}/estates/{estate['id']}/probate/facts", json=FACTS)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["determination"]["track"] == "informal_testate"
    assert body["determination"]["forms"] == [2, 3, 4, 5, 7]
    assert body["facts"]["date_of_death"] == "2025-01-15"
    assert body["facts"]["probate_property_value"] == "250000.00"
    assert body["facts"]["heirs"][1]["name"] == "Bob Olson"
    assert body["anchors"]["date_of_death"] == "2025-01-15"
    assert [row for row in body["forms"] if row["required"]][0]["pages"] == [26, 28]
    assert body["deadlines_preview"]["waiting_on"]["appointment_date"]

    row = await db_session.get(Estate, uuid.UUID(estate["id"]))
    assert row.probate_track == "informal_testate"
    assert row.date_of_death == date(2025, 1, 15)
    assert row.domicile_county == "Cass"
    assert row.will_execution_date == date(2010, 5, 6)
    assert row.grantor == "Ole Olson"
    assert row.gross_estate_value == 250000
    events = (
        (
            await db_session.execute(
                select(EstateEvent).where(EstateEvent.estate_id == row.id)
            )
        )
        .scalars()
        .all()
    )
    assert any(event.event_type == "probate" for event in events)

    # The estate list now reports the domicile county as present.
    listed = await client.get(f"{BASE}/estates/{estate['id']}")
    assert listed.json()["probate_track"] == "informal_testate"
    assert "Domicile county" not in listed.json()["missing_facts"]


@pytest.mark.asyncio
async def test_a_partial_update_keeps_what_it_did_not_name_and_clears_what_it_blanked(
    client,
):
    estate = await _estate(client)
    await client.put(f"{BASE}/estates/{estate['id']}/probate/facts", json=FACTS)
    changed = await client.put(
        f"{BASE}/estates/{estate['id']}/probate/facts",
        json={"date_of_death": "2022-01-15", "will_original_available": None},
    )
    body = changed.json()
    assert body["determination"]["track"] == "formal_testate_late"
    assert body["facts"]["decedent_name"] == "Ole Olson"
    assert body["facts"]["will_original_available"] is None
    assert body["determination"]["checklist"]
    assert body["determination"]["forms"] == []


@pytest.mark.asyncio
async def test_recompute_and_anchors_move_the_clock_without_touching_facts(client):
    estate = await _estate(client)
    await client.put(f"{BASE}/estates/{estate['id']}/probate/facts", json=FACTS)
    anchored = await client.patch(
        f"{BASE}/estates/{estate['id']}/probate/anchors",
        json={"appointment_date": "2025-03-31", "first_publication_date": "2025-04-07"},
    )
    assert anchored.status_code == 200, anchored.text
    preview = anchored.json()["deadlines_preview"]
    due = {item["deadline_type"]: item["due_date"] for item in preview["deadlines"]}
    assert due["notice_heirs"] == "2025-04-30"
    assert due["creditor_bar"] == "2025-07-07"
    assert due["inventory"] == "2025-10-15"
    assert anchored.json()["facts"]["decedent_name"] == "Ole Olson"

    recomputed = await client.post(f"{BASE}/estates/{estate['id']}/probate/determine")
    assert recomputed.status_code == 200
    assert recomputed.json()["determination"]["track"] == "informal_testate"


@pytest.mark.asyncio
async def test_deadline_sync_is_idempotent_and_can_mirror_tasks(
    client, db_session, test_tenant, test_user
):
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"probate-{uuid.uuid4().hex[:8]}",
        matter_name="Olson probate",
        matter_type="probate",
        status="open",
    )
    db_session.add(matter)
    await db_session.commit()
    estate = await _estate(client, matter_id=str(matter.id))
    unready = await client.post(
        f"{BASE}/estates/{estate['id']}/probate/deadlines/sync", json={}
    )
    assert unready.status_code == 409

    await client.put(f"{BASE}/estates/{estate['id']}/probate/facts", json=FACTS)
    await client.patch(
        f"{BASE}/estates/{estate['id']}/probate/anchors",
        json={"appointment_date": "2025-03-31"},
    )
    first = await client.post(
        f"{BASE}/estates/{estate['id']}/probate/deadlines/sync",
        json={"mirror_tasks": True},
    )
    assert first.status_code == 200, first.text
    assert set(first.json()["created"]) >= {"notice_heirs", "inventory", "tax_706"}
    assert "creditor_bar" in first.json()["waiting_on"]["first_publication_date"]

    rows = (
        (
            await db_session.execute(
                select(EstateDeadline).where(
                    EstateDeadline.estate_id == uuid.UUID(estate["id"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == len(first.json()["created"])
    notice = next(row for row in rows if row.deadline_type == "notice_heirs")
    assert notice.due_date == date(2025, 4, 30)
    assert "30.1-18-05" in notice.notes
    tasks = (
        (await db_session.execute(select(Task).where(Task.matter_id == matter.id)))
        .scalars()
        .all()
    )
    assert {task.external_ref for task in tasks} == {
        f"estate_deadline:{row.id}" for row in rows
    }

    # A completed row is left alone; the rest move with the anchor.
    notice.status = "complete"
    await db_session.commit()
    await client.patch(
        f"{BASE}/estates/{estate['id']}/probate/anchors",
        json={"appointment_date": "2025-04-30"},
    )
    second = await client.post(
        f"{BASE}/estates/{estate['id']}/probate/deadlines/sync", json={}
    )
    assert second.json()["created"] == []
    assert "notice_heirs" in second.json()["unchanged"]
    assert "hhs_affidavit" in second.json()["updated"]
    await db_session.refresh(notice)
    assert notice.due_date == date(2025, 4, 30)
    again = (
        (
            await db_session.execute(
                select(EstateDeadline).where(
                    EstateDeadline.estate_id == uuid.UUID(estate["id"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(again) == len(rows)


@pytest.mark.asyncio
async def test_pulling_from_intake_reads_the_probate_questionnaire(
    client, db_session, test_tenant, test_user, monkeypatch
):
    contact = Contact(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        first_name="Ann",
        last_name="Olson",
        email="ann@example.com",
    )
    db_session.add(contact)
    await db_session.flush()
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"probate-{uuid.uuid4().hex[:8]}",
        matter_name="Olson probate",
        matter_type="probate",
        client_contact_id=contact.id,
        status="open",
    )
    db_session.add(matter)
    await db_session.commit()
    monkeypatch.setattr(
        intake_service,
        "store_file",
        AsyncMock(
            return_value=SimpleNamespace(
                succeeded=True,
                storage_path="provider/path",
                provider="google_drive",
                backend="google_drive",
                provider_item_id="item",
                drive_id="drive",
                parent_id="parent",
            )
        ),
    )
    monkeypatch.setattr(
        intake_service,
        "get_user_capabilities",
        AsyncMock(return_value={"manage_matters"}),
    )
    user = SimpleNamespace(
        id=test_user.id, tenant_id=test_user.tenant_id, role=test_user.role
    )
    options = IntakeStart(
        email=contact.email,
        channels=["email"],
        include_questionnaire=True,
        questions=intake_starter_pack.questionnaire("probate"),
        confirm_send=True,
    )
    packet = await intake_service.start_packet(
        db_session, user, matter, options, "fee.pdf", b"%PDF-reviewed"
    )
    packet.answers = {
        "decedent_name": "Ole Olson",
        "date_of_death": "2025-01-15",
        "domicile_state": "North Dakota",
        "domicile_county": "Cass",
        "will_exists": "no",
        "real_property_in_nd": "yes",
        "probate_property_value": "300000",
        "applicant_name": "Ann Olson",
        "applicant_relationship": "spouse",
        "heirs_list": "Ann Olson; 70; spouse; Fargo\nBob Olson; 45; son; Moorhead",
        "prior_appointment": "no",
        "probate_opened_elsewhere": "no",
        "demand_for_notice": "no",
    }
    await db_session.commit()

    unlinked = await _estate(client)
    refused = await client.post(
        f"{BASE}/estates/{unlinked['id']}/probate/facts/from-intake", json={}
    )
    assert refused.status_code == 409

    estate = await _estate(client, matter_id=str(matter.id))
    await client.put(
        f"{BASE}/estates/{estate['id']}/probate/facts",
        json={"decedent_name": "O. Olson", "applicant_phone": "701-555-0100"},
    )
    pulled = await client.post(
        f"{BASE}/estates/{estate['id']}/probate/facts/from-intake", json={}
    )
    assert pulled.status_code == 200, pulled.text
    body = pulled.json()
    assert body["facts"]["decedent_name"] == "O. Olson"  # staff entry kept
    assert body["facts"]["applicant_phone"] == "701-555-0100"
    assert body["facts"]["will_exists"] is False
    assert body["facts"]["heirs"][1]["relationship"] == "son"
    assert body["determination"]["track"] == "informal_intestate"
    assert body["sources"][0]["kind"] == "portal_questionnaire"

    overwritten = await client.post(
        f"{BASE}/estates/{estate['id']}/probate/facts/from-intake",
        json={"overwrite": True},
    )
    assert overwritten.json()["facts"]["decedent_name"] == "Ole Olson"


async def _grant_manage_documents(db_session, test_tenant, test_user) -> None:
    from app.models.rbac import Role, UserRole

    role = Role(
        tenant_id=test_tenant.id,
        name="Document managers",
        capabilities=["manage_documents"],
    )
    db_session.add(role)
    await db_session.flush()
    db_session.add(
        UserRole(
            user_id=test_user.id,
            role_id=role.id,
            tenant_id=test_tenant.id,
            source="manual",
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_the_forms_pack_installs_once_from_the_shipped_sample(
    client, db_session, test_tenant, test_user, monkeypatch, tmp_path
):
    monkeypatch.setattr(document_templates.settings, "UPLOAD_DIR", str(tmp_path))
    await _grant_manage_documents(db_session, test_tenant, test_user)
    manifest = json.loads((SEED_DIR / "manifest.json").read_text())
    entry = next(
        f for f in manifest["forms"] if f["slug"] == forms_module.GUIDEBOOK_SLUG
    )
    content = (SEED_DIR / entry["filename"]).read_bytes()
    db_session.add(
        SampleTemplate(
            id=uuid.uuid4(),
            slug=entry["slug"],
            title=entry["title"],
            category=entry["category"],
            jurisdictions=entry["jurisdictions"],
            description=entry["description"],
            format="pdf",
            source_filename=entry["filename"],
            source_sha256=hashlib.sha256(content).hexdigest(),
            source_file_size=len(content),
            field_count=entry["field_count"],
            variable_schema={"version": 1, "fields": [], "source": "sample_library"},
            provenance=entry["provenance"],
            is_active=True,
        )
    )
    await db_session.commit()

    listed = await client.get(f"{BASE}/probate/forms")
    assert listed.status_code == 200, listed.text
    rows = listed.json()["forms"]
    guidebook_rows = [row for row in rows if row["slug"] == forms_module.GUIDEBOOK_SLUG]
    assert len(guidebook_rows) == 19
    assert all(row["template_id"] for row in guidebook_rows)
    assert all(row["template_status"] == "draft" for row in guidebook_rows)
    assert not any(row["published"] for row in guidebook_rows)
    companions = [row for row in rows if row["number"] is None]
    assert len(companions) == len(forms_module.PACK_SAMPLES) - 1
    assert all(row["template_id"] is None for row in companions)

    installed = await client.post(f"{BASE}/probate/forms/install")
    assert installed.status_code == 200, installed.text
    body = installed.json()
    assert [item["created"] for item in body["templates"]] == [False]
    assert set(body["missing_samples"]) == {
        slug for slug, *_ in forms_module.PACK_SAMPLES[1:]
    }

    templates = (
        (
            await db_session.execute(
                select(DocumentTemplate).where(
                    DocumentTemplate.tenant_id == test_tenant.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(templates) == 1
    template = templates[0]
    assert template.format == "pdf"
    assert template.is_active is False
    assert template.module == "trust-estate"
    assert template.source_provenance["sample_slug"] == forms_module.GUIDEBOOK_SLUG
    assert Path(template.source_storage_path).read_bytes() == content


@pytest.mark.asyncio
async def test_the_state_reports_its_resolved_jurisdiction(client):
    estate = await _estate(client)
    state = await client.get(f"{BASE}/estates/{estate['id']}/probate")
    assert state.status_code == 200, state.text
    body = state.json()
    assert body["jurisdiction"] == "ND"
    assert body["jurisdiction_label"] == "North Dakota"
    assert body["jurisdiction_supported"] is True


@pytest.mark.asyncio
async def test_an_unsupported_jurisdiction_fails_closed(client, db_session):
    estate = await _estate(client, jurisdiction="Minnesota")
    state = await client.get(f"{BASE}/estates/{estate['id']}/probate")
    assert state.status_code == 200, state.text
    body = state.json()
    assert body["jurisdiction_supported"] is False
    assert body["forms"] == []
    assert body["deadlines_preview"]["deadlines"] == []
    # A write that would apply the wrong state's rules is refused.
    refused = await client.put(
        f"{BASE}/estates/{estate['id']}/probate/facts", json={"will_exists": True}
    )
    assert refused.status_code == 409

    listed = await client.get(f"{BASE}/probate/forms", params={"jurisdiction": "MN"})
    assert listed.status_code == 422


@pytest.mark.asyncio
async def test_a_portal_client_token_cannot_reach_the_staff_workbench(
    client, db_session, test_tenant
):
    """A role="client" login must not replay its token against staff routes."""

    from app.models.user import User
    from app.services.portal_token import create_user_token

    client_user = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="portal-client@testfirm.com",
        full_name="Portal Client",
        role="client",
        is_active=True,
        license_active=True,
    )
    db_session.add(client_user)
    await db_session.commit()
    token = create_user_token(
        user_id=str(client_user.id),
        tenant_id=str(test_tenant.id),
        role="client",
        email=client_user.email,
    )
    headers = {"Authorization": f"Bearer {token}"}

    read = await client.get(f"{BASE}/probate/forms", headers=headers)
    assert read.status_code == 403
    write = await client.put(
        f"{BASE}/estates/{uuid.uuid4()}/probate/facts", json={}, headers=headers
    )
    assert write.status_code == 403
    verify = await client.post(
        f"{BASE}/estates/{uuid.uuid4()}/assets/{uuid.uuid4()}/verify",
        json={"verification_status": "verified"},
        headers=headers,
    )
    assert verify.status_code == 403
