"""Bulk matter creation from the CSV template, against the real database."""

import csv
import io
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select

from app.models.contact import Contact
from app.models.external_import import ExternalRecordLink
from app.models.matter_assignment import MatterAssignment
from app.models.plugin import Matter, MatterEvent
from app.models.user import User
from app.routers import matter_csv_imports as routes
from app.services.csv_upload import csv_safe, read_csv_rows

HEADER = ",".join(routes.TEMPLATE_COLUMNS)


def staff(test_user):
    return SimpleNamespace(
        id=test_user.id,
        tenant_id=test_user.tenant_id,
        role="admin",
        full_name="Test Attorney",
        email=test_user.email,
    )


def sheet(*rows, header=HEADER):
    """Rows as dicts keyed by template column; missing columns are blank."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    columns = header.split(",")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return buffer.getvalue().encode()


async def preview(db_session, user, content, *, run_id=None, filename="matters.csv"):
    return await routes.preview(
        UploadFile(file=io.BytesIO(content), filename=filename),
        run_id,
        db_session,
        user,
    )


async def confirm(db_session, user, run_id, include=None):
    return await routes.confirm(
        uuid.UUID(run_id) if isinstance(run_id, str) else run_id,
        routes.ConfirmBody(confirm=True, include_rows=include),
        db_session,
        user,
    )


def test_csv_helpers_neutralise_formula_cells_and_bound_the_sheet():
    assert csv_safe("=SUM(A1)") == "'=SUM(A1)"
    assert csv_safe("+1") == "'+1" and csv_safe("plain") == "plain" and csv_safe(None) == ""
    headers, rows = read_csv_rows(
        # A BOM, a spaced header, a comma-only line and a trailing blank line
        # are all spreadsheet artefacts the reader absorbs.
        b"\xef\xbb\xbfMatter Name, client_email\nSmith,jane@x.com\n,\n\n",
        max_bytes=1024,
        max_rows=10,
    )
    assert headers == ["matter_name", "client_email"]
    assert rows == [{"matter_name": "Smith", "client_email": "jane@x.com"}, {}]
    for raw, message in (
        (b"", "empty"),
        (b"a" * 2000, "limit"),
        (b"\xff\xfe", "UTF-8"),
        (b"a,a\n1,2\n", "unique"),
        (b"a,b\n1,2,3\n", "more values"),
    ):
        with pytest.raises(ValueError, match=message):
            read_csv_rows(raw, max_bytes=1024, max_rows=10)
    with pytest.raises(ValueError, match="row limit"):
        read_csv_rows(b"a\n1\n2\n", max_bytes=1024, max_rows=1)


@pytest.mark.asyncio
async def test_template_download(test_user):
    result = await routes.template(staff(test_user))
    assert result.media_type.startswith("text/csv")
    assert 'filename="matters-template.csv"' in result.headers["content-disposition"]
    body = result.body.decode()
    assert body.splitlines()[0] == HEADER
    assert "Smith v. Acme Corp" in body


@pytest.mark.asyncio
async def test_preview_resolves_clients_staff_and_problems(db_session, test_user):
    user = staff(test_user)
    existing = Contact(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        contact_type="client",
        first_name="Jane",
        last_name="Smith",
        email="Jane@Example.com",
        client_number="C-100",
    )
    other = Contact(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        contact_type="client",
        first_name="Other",
        last_name="Person",
        email="other@example.com",
        client_number="C-200",
    )
    db_session.add_all([existing, other])
    await db_session.commit()

    content = sheet(
        {"matter_name": "By email", "client_email": "JANE@example.com", "attorney_email": test_user.email.upper()},
        {"matter_name": "By number", "client_number": "C-100", "engagement": "review"},
        {"matter_name": "By id", "client_id": str(existing.id)},
        {"matter_name": "Ambiguous", "client_number": "C-100", "client_email": "other@example.com"},
        {"matter_name": "New org", "client_organization": "Jones LLC", "opened_on": "2024-02-10", "agreement": "no_agreement", "agreement_note": "Handshake"},
        {"matter_name": "Same org again", "client_organization": "jones llc"},
        {"matter_name": "", "client_first_name": "No", "client_last_name": "Name", "status": "weird", "opened_on": "2999-01-01", "engagement": "nope", "attorney_email": "ghost@example.com", "hourly_rate": "abc", "client_id": "nope"},
        {"matter_name": "No client"},
        {"matter_name": "Wrong agreement", "client_email": "a@b.com", "engagement": "review", "agreement": "no_agreement", "agreement_note": "x"},
        {"matter_name": "Note missing", "client_email": "b@b.com", "agreement": "signed_no_copy"},
        {"matter_name": "Signed none", "client_email": "c@b.com", "agreement": "no_agreement", "agreement_note": "why", "agreement_signed_on": "2020-01-01"},
        {"matter_name": "x" * 501, "client_email": "d@b.com"},
    )
    result = await preview(db_session, user, content)
    rows = {row["values"]["matter_name"][:20]: row for row in result["rows"]}

    assert result["status"] == "review"
    assert rows["By email"]["contact"] == {"action": "match", "contact_id": str(existing.id), "display_name": "Jane Smith", "key": None}
    assert rows["By email"]["attorney"] == {"user_id": str(test_user.id), "name": "Test Attorney"}
    assert rows["By email"]["errors"] == []
    assert rows["By email"]["values"]["agreement"] == "pending_copy"
    assert rows["By number"]["contact"]["contact_id"] == str(existing.id)
    assert rows["By number"]["values"]["agreement"] is None
    assert rows["By id"]["contact"]["action"] == "match"
    assert rows["Ambiguous"]["errors"] == ["client: the client number and email name different contacts; review required"]
    assert rows["New org"]["contact"] == {"action": "create", "contact_id": None, "display_name": "Jones LLC", "key": "org:jones llc"}
    assert rows["New org"]["errors"] == []
    assert rows["Same org again"]["contact"]["action"] == "create_shared"
    problems = rows[""]["errors"]
    assert "matter_name: required" in problems
    assert "status: use open, active or pending" in problems
    assert "opened_on: cannot be in the future" in problems
    assert "engagement: use existing, review or required" in problems
    assert "attorney_email: no active staff member with this email" in problems
    assert "hourly_rate: use a number" in problems
    assert "client_id: not a contact ID" in problems
    assert rows["No client"]["errors"] == ["client: give a client number, email, name or organization"]
    assert rows["Wrong agreement"]["errors"] == ["agreement: only an existing engagement records an agreement"]
    assert rows["Note missing"]["errors"] == ["agreement_note: say where it was signed"]
    assert rows["Signed none"]["errors"] == ["agreement_signed_on: a matter with no fee agreement has no signing date"]
    assert any(error.startswith("matter_name:") for error in rows["x" * 20]["errors"])
    assert result["summary"] == {
        "total": 12,
        "valid": 5,
        "invalid": 7,
        "contacts_matched": 3,
        "contacts_to_create": 6,
    }


@pytest.mark.asyncio
async def test_preview_bounds_and_replay(db_session, test_user):
    user = staff(test_user)
    with pytest.raises(HTTPException) as caught:
        await preview(db_session, user, b"matter_name\nx\n", filename="matters.txt")
    assert caught.value.status_code == 400
    with pytest.raises(HTTPException) as caught:
        await preview(db_session, user, b"\xff\xfe")
    assert caught.value.status_code == 400
    with pytest.raises(HTTPException) as caught:
        await preview(db_session, user, b"client_email\nx@y.com\n")
    assert "matter_name column" in caught.value.detail
    with pytest.raises(HTTPException) as caught:
        await preview(db_session, user, b"matter_name\n" + b"x\n" * (routes.MAX_ROWS + 1))
    assert caught.value.status_code == 413
    with pytest.raises(HTTPException) as caught:
        await preview(db_session, user, b"matter_name\n" + b"x" * (routes.MAX_BYTES + 1))
    assert caught.value.status_code == 413

    run_id = uuid.uuid4()
    content = sheet({"matter_name": "Smith", "client_email": "a@b.com", "unknown": "1"}, header=HEADER + ",extra")
    first = await preview(db_session, user, content, run_id=run_id)
    assert first["id"] == str(run_id)
    assert first["ignored_columns"] == ["extra"]
    again = await preview(db_session, user, content, run_id=run_id)
    assert again == first
    with pytest.raises(HTTPException) as caught:
        await preview(db_session, user, sheet({"matter_name": "Different"}), run_id=run_id)
    assert caught.value.status_code == 409
    # Another user cannot see, reuse or confirm the run.
    stranger = SimpleNamespace(id=uuid.uuid4(), tenant_id=user.tenant_id, role="admin")
    with pytest.raises(HTTPException) as caught:
        await routes.status(run_id, db_session, stranger)
    assert caught.value.status_code == 404
    with pytest.raises(HTTPException) as caught:
        await preview(db_session, stranger, content, run_id=run_id)
    assert caught.value.status_code == 409


@pytest.mark.asyncio
async def test_confirm_creates_contacts_and_matters_once(db_session, test_user, test_tenant):
    user = staff(test_user)
    partner = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="partner@testfirm.com",
        full_name="Pat Partner",
        role="user",
        oauth_provider="google",
        oauth_subject="google-sub-partner",
        is_active=True,
    )
    existing = Contact(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        contact_type="client",
        first_name="Jane",
        last_name="Smith",
        email="jane@example.com",
    )
    db_session.add_all([partner, existing])
    await db_session.commit()
    content = sheet(
        {
            "matter_name": "Smith v. Acme",
            "client_email": "jane@example.com",
            "opened_on": "2024-02-10",
            "agreement_signed_on": "2024-02-01",
            "attorney_email": "partner@testfirm.com",
            "partner_attorney_email": test_user.email,
            "hourly_rate": "$1,250.50",
            "status": "active",
            "case_number": "24-CV-1",
        },
        {
            "matter_name": "Jones lease",
            "client_organization": "Jones LLC",
            "client_email": "office@jones.example",
            "agreement": "no_agreement",
            "agreement_note": "Handshake arrangement",
        },
        {
            "matter_name": "Jones sale",
            "client_organization": "Jones LLC",
            "client_email": "office@jones.example",
            "engagement": "required",
        },
        {"matter_name": "Broken", "client_email": "x@y.com", "opened_on": "not-a-date"},
        {"matter_name": "Excluded", "client_first_name": "Ex", "client_last_name": "Cluded"},
    )
    previewed = await preview(db_session, user, content)
    run_id = previewed["id"]
    by_name = {row["values"]["matter_name"]: row["row"] for row in previewed["rows"]}

    with pytest.raises(HTTPException) as caught:
        await confirm(db_session, user, run_id)
    assert caught.value.status_code == 422 and str(by_name["Broken"]) in caught.value.detail
    with pytest.raises(HTTPException) as caught:
        await confirm(db_session, user, run_id, include=[999])
    assert caught.value.status_code == 422

    include = [by_name[name] for name in ("Smith v. Acme", "Jones lease", "Jones sale")]
    result = await confirm(db_session, user, run_id, include=include)
    assert result["status"] == "complete"
    assert [r["matter_name"] for r in result["results"]] == ["Smith v. Acme", "Jones lease", "Jones sale"]
    assert [r["contact_created"] for r in result["results"]] == [False, True, False]
    assert result["summary"]["created_matters"] == 3 and result["summary"]["created_contacts"] == 1

    smith = await db_session.get(Matter, uuid.UUID(result["results"][0]["matter_id"]))
    assert smith.matter_number and smith.client_contact_id == existing.id
    assert smith.opened_on == date(2024, 2, 10)
    assert smith.retention_until == date(2024, 2, 10) + timedelta(days=365 * 7)
    assert smith.status == "active" and smith.stage == "Active"
    assert smith.source == "csv_import" and smith.case_number == "24-CV-1"
    assert smith.hourly_rate == 1250.5
    assert smith.attorney_of_record_id == partner.id and smith.partner_attorney_id == test_user.id
    assert smith.engagement_status == "pending_copy"
    assert smith.engagement_signed_on == date(2024, 2, 1)
    assignments = {
        (a.user_id, a.role, a.is_primary)
        for a in (
            await db_session.scalars(
                select(MatterAssignment).where(MatterAssignment.matter_id == smith.id)
            )
        ).all()
    }
    assert assignments == {(partner.id, "lead_attorney", True), (test_user.id, "associate", False)}

    lease = await db_session.get(Matter, uuid.UUID(result["results"][1]["matter_id"]))
    sale = await db_session.get(Matter, uuid.UUID(result["results"][2]["matter_id"]))
    assert lease.client_contact_id == sale.client_contact_id
    jones = await db_session.get(Contact, lease.client_contact_id)
    assert jones.organization_name == "Jones LLC" and jones.entity_type == "organization"
    assert jones.email == "office@jones.example" and jones.contact_type == "client"
    assert lease.engagement_status == "no_agreement" and lease.engagement_note == "Handshake arrangement"
    assert lease.opened_on == date.today()
    assert sale.stage == "Intake / Awaiting Documents" and sale.engagement_status is None
    lease_titles = set(
        (await db_session.execute(select(MatterEvent.title).where(MatterEvent.matter_id == lease.id))).scalars()
    )
    assert lease_titles == {"Existing matter imported", "Matter opened without a fee agreement"}
    assert (
        await db_session.scalar(
            select(func.count()).select_from(ExternalRecordLink).where(ExternalRecordLink.import_run_id == uuid.UUID(run_id))
        )
        == 4
    )
    # Neither the excluded row nor the broken one became a matter.
    assert await db_session.scalar(select(func.count()).select_from(Matter).where(Matter.tenant_id == user.tenant_id)) == 3

    # Replaying the confirmation returns the same result without creating more.
    again = await confirm(db_session, user, run_id)
    assert again["results"] == result["results"]
    assert (await routes.status(uuid.UUID(run_id), db_session, user))["results"] == result["results"]
    assert await db_session.scalar(select(func.count()).select_from(Matter).where(Matter.tenant_id == user.tenant_id)) == 3


@pytest.mark.asyncio
async def test_confirm_refuses_a_stale_preview(db_session, test_user):
    user = staff(test_user)
    existing = Contact(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        contact_type="client",
        first_name="Gone",
        last_name="Soon",
        email="gone@example.com",
    )
    db_session.add(existing)
    await db_session.commit()
    previewed = await preview(db_session, user, sheet({"matter_name": "Stale", "client_email": "gone@example.com"}))
    await db_session.delete(existing)
    await db_session.commit()
    with pytest.raises(HTTPException) as caught:
        await confirm(db_session, user, previewed["id"])
    assert caught.value.status_code == 409
    assert (await routes.status(uuid.UUID(previewed["id"]), db_session, user))["status"] == "review"
