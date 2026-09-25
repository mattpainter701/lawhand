"""Client-portal logins cannot use the staff matter-document API.

A portal client is a real ``User`` (``role="client"``) whose token
``get_current_user`` accepts, and portal responses expose shared document IDs.
Every staff document, folder, tag, fact and search route must refuse that user
before touching the database or a storage provider; clients use ``/api/portal``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from jose import jwt as jose_jwt
from sqlalchemy import func, select

from app.config import get_settings
from app.models.matter_document import MatterDocument
from app.models.matter_document_folder import MatterDocumentFolder
from app.models.matter_document_tag import MatterDocumentTag
from app.models.plugin import Matter
from app.models.user import User
from app.routers import matter_documents as routes
from app.services.access_control import is_client_portal_user, require_firm_staff

API = "/api/matters"


@pytest_asyncio.fixture
async def matter(db_session, test_tenant, test_user):
    row = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"staff-only-{uuid.uuid4().hex[:8]}",
        matter_name="Atlas acquisition",
        matter_type="corporate",
        status="open",
    )
    db_session.add(row)
    await db_session.commit()
    return SimpleNamespace(id=row.id, tenant_id=test_tenant.id, user_id=test_user.id)


@pytest_asyncio.fixture
async def document_id(db_session, matter) -> uuid.UUID:
    row = MatterDocument(
        id=uuid.uuid4(),
        tenant_id=matter.tenant_id,
        matter_id=matter.id,
        uploaded_by_user_id=matter.user_id,
        filename="Engagement letter.pdf",
        content_type="application/pdf",
        file_size=10,
        storage_path="matters/engagement-letter.pdf",
        description="Firm copy",
        portal_visible=True,
    )
    db_session.add(row)
    await db_session.commit()
    return row.id


@pytest_asyncio.fixture
async def folder_id(db_session, matter) -> uuid.UUID:
    row = MatterDocumentFolder(
        id=uuid.uuid4(),
        tenant_id=matter.tenant_id,
        matter_id=matter.id,
        name="Correspondence",
        path="Correspondence",
    )
    db_session.add(row)
    await db_session.commit()
    return row.id


@pytest_asyncio.fixture
async def client_headers(db_session, matter) -> dict[str, str]:
    portal_user = User(
        id=uuid.uuid4(),
        tenant_id=matter.tenant_id,
        email="client@example.test",
        full_name="Portal Client",
        role="client",
        is_active=True,
    )
    db_session.add(portal_user)
    await db_session.commit()
    settings = get_settings()
    token = jose_jwt.encode(
        {
            "sub": str(portal_user.id),
            "tenant_id": str(matter.tenant_id),
            "role": "client",
            "email": "client@example.test",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def provider_calls(monkeypatch):
    """Record any storage read, write or delete a refused request attempts."""
    calls: list[str] = []
    store = routes.matter_file_store
    for name in (
        "read_matter_file_bytes",
        "get_matter_file_open_url",
        "get_matter_file_metadata",
        "replace_matter_file_content",
        "delete_stored_result",
        "store_matter_file",
        "store_matter_file_result",
    ):

        async def record(*_args, _name=name, **_kwargs):
            calls.append(_name)
            raise AssertionError(f"{_name} must not run for a client")

        monkeypatch.setattr(store, name, record)
    return calls


def _staff_routes(matter_id, doc_id, folder_id):
    doc = f"{API}/{matter_id}/documents/{doc_id}"
    folders = f"{API}/{matter_id}/document-folders"
    tag_id = uuid.uuid4()
    return [
        # Reads
        ("GET", f"{API}/{matter_id}/documents", {}),
        ("GET", f"{doc}/download", {}),
        ("GET", f"{doc}/open", {}),
        ("GET", f"{API}/{matter_id}/documents/search", {"params": {"q": "letter"}}),
        ("GET", f"{doc}/facts/form-sources", {}),
        ("GET", folders, {}),
        ("GET", "/api/document-tags", {}),
        # Writes
        (
            "POST",
            f"{API}/{matter_id}/documents/upload",
            {"files": {"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}},
        ),
        (
            "PATCH",
            doc,
            {"json": {"description": "client edit", "portal_visible": False}},
        ),
        ("DELETE", doc, {}),
        ("POST", f"{doc}/facts", {}),
        (
            "POST",
            f"{doc}/facts/from-form",
            {"json": {"template_id": str(uuid.uuid4())}},
        ),
        ("POST", f"{doc}/facts/accept", {"json": {"target_key": "x", "value": "y"}}),
        ("POST", f"{doc}/cloud-edit", {"json": {}}),
        ("POST", f"{doc}/reconcile", {"json": {}}),
        (
            "POST",
            f"{doc}/revised-version",
            {"files": {"file": ("x.docx", b"PK", "application/octet-stream")}},
        ),
        ("POST", folders, {"json": {"name": "Client folder"}}),
        ("PATCH", f"{folders}/{folder_id}", {"json": {"name": "Renamed"}}),
        ("DELETE", f"{folders}/{folder_id}", {}),
        (
            "POST",
            f"{API}/{matter_id}/documents/move",
            {"json": {"document_ids": [str(doc_id)], "folder_id": str(folder_id)}},
        ),
        (
            "POST",
            f"{API}/{matter_id}/documents/copy",
            {"json": {"document_id": str(doc_id), "copy_id": str(uuid.uuid4())}},
        ),
        ("POST", "/api/document-tags", {"json": {"name": "Client tag"}}),
        ("PATCH", f"/api/document-tags/{tag_id}", {"json": {"name": "x"}}),
        ("DELETE", f"/api/document-tags/{tag_id}", {}),
        ("PUT", f"{doc}/tags", {"json": {"tag_ids": []}}),
    ]


async def test_client_portal_users_are_refused_on_every_staff_document_route(
    client, db_session, matter, document_id, folder_id, client_headers, provider_calls
):
    for method, url, kwargs in _staff_routes(matter.id, document_id, folder_id):
        resp = await client.request(method, url, headers=client_headers, **kwargs)
        assert resp.status_code == 403, (
            f"{method} {url}: {resp.status_code} {resp.text}"
        )
        assert resp.json()["detail"]["code"] == "staff_only", f"{method} {url}"

    assert provider_calls == []
    db_session.expire_all()
    doc = await db_session.get(MatterDocument, document_id)
    assert doc is not None
    assert doc.description == "Firm copy"
    assert doc.portal_visible is True
    assert doc.folder_id is None
    doc_count = await db_session.scalar(
        select(func.count())
        .select_from(MatterDocument)
        .where(MatterDocument.matter_id == matter.id)
    )
    assert doc_count == 1
    folder = await db_session.get(MatterDocumentFolder, folder_id)
    assert folder is not None and folder.name == "Correspondence"
    folder_count = await db_session.scalar(
        select(func.count())
        .select_from(MatterDocumentFolder)
        .where(MatterDocumentFolder.matter_id == matter.id)
    )
    assert folder_count == 1
    tag_count = await db_session.scalar(
        select(func.count())
        .select_from(MatterDocumentTag)
        .where(MatterDocumentTag.tenant_id == matter.tenant_id)
    )
    assert tag_count == 0


async def test_client_portal_users_cannot_reach_document_revisions(
    client, matter, document_id, client_headers
):
    resp = await client.get(
        f"{API}/{matter.id}/documents/{document_id}/revisions", headers=client_headers
    )
    assert resp.status_code == 403


async def test_firm_staff_still_read_and_write_matter_documents(
    client, db_session, matter, document_id, folder_id
):
    listed = await client.get(f"{API}/{matter.id}/documents")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [str(document_id)]

    folders = await client.get(f"{API}/{matter.id}/document-folders")
    assert folders.status_code == 200, folders.text

    tags = await client.get("/api/document-tags")
    assert tags.status_code == 200, tags.text

    updated = await client.patch(
        f"{API}/{matter.id}/documents/{document_id}",
        json={"description": "Signed copy"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["description"] == "Signed copy"

    created = await client.post(
        f"{API}/{matter.id}/document-folders", json={"name": "Pleadings"}
    )
    assert created.status_code == 201, created.text

    moved = await client.post(
        f"{API}/{matter.id}/documents/move",
        json={"document_ids": [str(document_id)], "folder_id": str(folder_id)},
    )
    assert moved.status_code == 200, moved.text

    db_session.expire_all()
    doc = await db_session.get(MatterDocument, document_id)
    assert doc.description == "Signed copy"
    assert doc.folder_id == folder_id


@pytest.mark.parametrize("role", ["client", "Client", " CLIENT "])
def test_require_firm_staff_refuses_client_roles(role):
    user = SimpleNamespace(role=role)
    assert is_client_portal_user(user)
    with pytest.raises(HTTPException) as exc:
        require_firm_staff(user)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "staff_only"


@pytest.mark.parametrize("role", ["admin", "user", "accountant", None, ""])
def test_require_firm_staff_allows_firm_roles(role):
    user = SimpleNamespace(role=role)
    assert not is_client_portal_user(user)
    require_firm_staff(user)
