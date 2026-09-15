"""One answer to "what can the client see?" across every surface.

Regression cover for #489. The portal overview counted ``portal_visible``
only, the documents tab served ``portal_visible`` *or* the recipient's intake
packet grants, and the staff tab labelled a grant-readable document "Private" —
three answers to one question. These tests pin the counts to each other and to
the rows actually served, and pin the label a signing grant produces.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from app.models.client_portal import ClientPortalInvite
from app.models.contact import Contact
from app.models.matter_document import MatterDocument
from app.models.matter_intake import MatterIntake
from app.models.matter_assignment import MatterAssignment
from app.models.plugin import Matter
from app.models.signature import SignatureRequest
from app.routers import client_portal as client_portal_router
from app.routers.client_portal import CLIENT_PORTAL_COOKIE_NAME
from app.services.portal_document_access import (
    ACCESS_CLIENT_UPLOAD,
    ACCESS_FIRM_SHARED,
    ACCESS_SIGNING_PACKET,
    document_access_source,
    matter_signing_grant_document_ids,
)
from app.services.portal_token import create_matter_portal_token

PORTAL = "/api/portal/client"


def _portal_headers(token: str) -> dict:
    return {"Cookie": f"{CLIENT_PORTAL_COOKIE_NAME}={token}", "Authorization": ""}


@pytest_asyncio.fixture
async def access_matter(db_session, test_tenant, test_user):
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"access-matter-{uuid.uuid4().hex[:8]}",
        matter_name="Nguyen v. Halbrook",
        matter_type="litigation",
        status="open",
        portal_enabled=True,
    )
    db_session.add(matter)
    db_session.add(
        MatterAssignment(
            id=uuid.uuid4(),
            tenant_id=test_tenant.id,
            matter_id=matter.id,
            user_id=test_user.id,
            role="lead",
            is_primary=True,
        )
    )
    await db_session.commit()
    await db_session.refresh(matter)
    return matter


def _document(tenant_id, matter_id, filename, *, uploaded_by=None, shared=False):
    return MatterDocument(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        matter_id=matter_id,
        uploaded_by_user_id=uploaded_by,
        filename=filename,
        content_type="application/pdf",
        file_size=1024,
        portal_visible=shared,
    )


@pytest_asyncio.fixture
async def access_documents(db_session, test_tenant, test_user, access_matter):
    """One document of each kind, plus a packet that grants one of them."""

    shared = _document(
        test_tenant.id, access_matter.id, "Shared brief.pdf",
        uploaded_by=test_user.id, shared=True,
    )
    private = _document(
        test_tenant.id, access_matter.id, "Internal strategy.pdf",
        uploaded_by=test_user.id,
    )
    fee_agreement = _document(
        test_tenant.id, access_matter.id, "Fee agreement.pdf",
        uploaded_by=test_user.id,
    )
    questionnaire = _document(
        test_tenant.id, access_matter.id, "Intake questionnaire.pdf",
        uploaded_by=test_user.id,
    )
    # The portal's own upload path marks a client's file portal_visible, which
    # is why the overview used to count it as something "shared" with them.
    client_upload = _document(
        test_tenant.id, access_matter.id, "Client photo.pdf", shared=True,
    )
    db_session.add_all([shared, private, fee_agreement, questionnaire, client_upload])

    raw_token = secrets.token_urlsafe(32)
    invite = ClientPortalInvite(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        matter_id=access_matter.id,
        contact_id=None,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        email="client@example.com",
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    signature = SignatureRequest(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        matter_id=access_matter.id,
        document_id=fee_agreement.id,
        status="sent",
        provider="internal",
        created_by_user_id=test_user.id,
    )
    contact = Contact(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        first_name="Dao",
        last_name="Nguyen",
        email="client@example.com",
    )
    db_session.add_all([invite, signature, contact])
    await db_session.flush()
    packet = MatterIntake(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        matter_id=access_matter.id,
        contact_id=contact.id,
        owner_id=test_user.id,
        created_by=test_user.id,
        signature_id=signature.id,
        invite_id=invite.id,
        encrypted_invite="encrypted",
        status="awaiting_documents",
        config={},
        requirements={
            "questionnaire": {
                "completed": False,
                "document_id": str(questionnaire.id),
            },
            "fee_agreement": {"completed": False},
        },
        answers={},
        delivery={},
    )
    db_session.add(packet)
    await db_session.commit()

    return {
        "invite": invite,
        "shared": shared,
        "private": private,
        "fee_agreement": fee_agreement,
        "questionnaire": questionnaire,
        "client_upload": client_upload,
    }


@pytest.fixture
def access_cookie(test_tenant, access_matter, access_documents):
    return create_matter_portal_token(
        tenant_id=str(test_tenant.id),
        matter_id=str(access_matter.id),
        contact_id=None,
        email=access_documents["invite"].email,
        invite_id=str(access_documents["invite"].id),
    )


def test_access_source_names_why_a_document_is_readable():
    staff_id = uuid.uuid4()
    document_id = uuid.uuid4()

    assert document_access_source(
        uploaded_by_user_id=None, portal_visible=False, signing_granted=False
    ) == ACCESS_CLIENT_UPLOAD
    assert document_access_source(
        uploaded_by_user_id=staff_id, portal_visible=True, signing_granted=False
    ) == ACCESS_FIRM_SHARED
    assert document_access_source(
        uploaded_by_user_id=staff_id, portal_visible=False, signing_granted=True
    ) == ACCESS_SIGNING_PACKET
    # A document that is neither shared nor granted is not readable at all, and
    # saying so is what keeps it out of every count.
    assert document_access_source(
        uploaded_by_user_id=staff_id, portal_visible=False, signing_granted=False
    ) is None
    assert document_id  # the id itself carries no access


@pytest.mark.asyncio
async def test_overview_count_equals_the_documents_the_tab_serves(
    client, access_cookie, access_documents
):
    headers = _portal_headers(access_cookie)

    overview = (await client.get(f"{PORTAL}/matter", headers=headers)).json()
    documents = (await client.get(f"{PORTAL}/documents", headers=headers)).json()

    assert overview["document_count"] == len(documents)
    # The private internal document is in neither.
    filenames = {doc["filename"] for doc in documents}
    assert "Internal strategy.pdf" not in filenames


@pytest.mark.asyncio
async def test_overview_breakdown_separates_shares_grants_and_client_uploads(
    client, access_cookie
):
    headers = _portal_headers(access_cookie)

    overview = (await client.get(f"{PORTAL}/matter", headers=headers)).json()

    assert overview["firm_shared_document_count"] == 1
    # The fee agreement behind the packet's signature request and the
    # questionnaire named by a requirement, neither of them shared.
    assert overview["signing_document_count"] == 2
    assert overview["client_upload_count"] == 1
    assert overview["document_count"] == 4
    assert overview["document_count"] == (
        overview["firm_shared_document_count"]
        + overview["signing_document_count"]
        + overview["client_upload_count"]
    )


@pytest.mark.asyncio
async def test_each_portal_document_says_why_the_client_can_read_it(
    client, access_cookie
):
    headers = _portal_headers(access_cookie)

    documents = (await client.get(f"{PORTAL}/documents", headers=headers)).json()
    by_name = {doc["filename"]: doc for doc in documents}

    assert by_name["Shared brief.pdf"]["access_source"] == ACCESS_FIRM_SHARED
    assert by_name["Fee agreement.pdf"]["access_source"] == ACCESS_SIGNING_PACKET
    assert by_name["Intake questionnaire.pdf"]["access_source"] == ACCESS_SIGNING_PACKET
    assert by_name["Client photo.pdf"]["access_source"] == ACCESS_CLIENT_UPLOAD


@pytest.mark.asyncio
async def test_staff_tab_marks_grant_readable_documents_instead_of_private(
    client, access_matter, access_documents
):
    listed = (
        await client.get(f"/api/matters/{access_matter.id}/documents")
    ).json()["items"]
    by_name = {doc["filename"]: doc for doc in listed}

    # This is the finding: the signing recipient can open these, so the staff
    # tab may not call them "Private".
    assert by_name["Fee agreement.pdf"]["portal_visible"] is False
    assert by_name["Fee agreement.pdf"]["signing_access"] is True
    assert by_name["Intake questionnaire.pdf"]["signing_access"] is True

    assert by_name["Internal strategy.pdf"]["signing_access"] is False
    # A shared document is described by its share, not by the grant.
    assert by_name["Shared brief.pdf"]["portal_visible"] is True
    assert by_name["Shared brief.pdf"]["signing_access"] is False


@pytest.mark.asyncio
async def test_a_revoked_invite_grants_nothing(
    db_session, test_tenant, access_matter, access_documents
):
    granted = await matter_signing_grant_document_ids(
        db_session, tenant_id=test_tenant.id, matter_ids=[access_matter.id]
    )
    assert access_documents["fee_agreement"].id in granted
    assert access_documents["questionnaire"].id in granted
    assert access_documents["private"].id not in granted

    access_documents["invite"].revoked = True
    await db_session.commit()

    assert await matter_signing_grant_document_ids(
        db_session, tenant_id=test_tenant.id, matter_ids=[access_matter.id]
    ) == set()


@pytest.mark.asyncio
async def test_signing_grants_do_widen_visibility_beyond_the_shared_set(
    client, access_cookie, access_documents
):
    """The issue asked for this verified either way. It does widen it."""

    headers = _portal_headers(access_cookie)
    documents = (await client.get(f"{PORTAL}/documents", headers=headers)).json()
    readable = {doc["filename"] for doc in documents}

    fee_agreement = access_documents["fee_agreement"]
    assert fee_agreement.portal_visible is False
    assert fee_agreement.filename in readable

    # Both a grant-readable and a private document 404 on missing bytes, so the
    # status alone proves nothing. What distinguishes them is whether the
    # request reaches storage at all.
    with patch.object(
        client_portal_router.matter_file_store,
        "read_matter_file_bytes",
        new=AsyncMock(return_value=b"%PDF-1.4 fee agreement"),
    ) as read_bytes:
        granted = await client.get(
            f"{PORTAL}/documents/{fee_agreement.id}/download", headers=headers
        )
        assert granted.status_code == 200
        assert read_bytes.await_count == 1

        # The boundary still holds: a private document nobody granted is
        # refused before storage is touched.
        private = access_documents["private"]
        assert private.filename not in readable
        denied = await client.get(
            f"{PORTAL}/documents/{private.id}/download", headers=headers
        )
        assert denied.status_code == 404
        assert read_bytes.await_count == 1
