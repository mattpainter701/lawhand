"""Router for matter file attachments (case documents)."""

import os
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.upload_guard import reject_oversized_request
from app.services.portal_document_access import matter_signing_grant_document_ids
from app.database import get_db, set_tenant_context
from app.middleware.tenant import get_current_user
from app.models.matter_document import MatterDocument
from app.models.matter_document_folder import MatterDocumentFolder
from app.models.matter_document_tag import MatterDocumentTagLink
from app.models.plugin import Matter
from app.models.user import User
from app.services.portal_client_alerts import (
    notify_client_portal_update,
    shared_document_headline,
)
from app.models.tenant import TenantSettings
from app.schemas.matter_document import (
    MatterDocumentCloudEditRequest,
    MatterDocumentCloudEditResponse,
    MatterDocumentListResponse,
    MatterDocumentResponse,
    MatterDocumentTagResponse,
    MatterDocumentUpdate,
)
from app.services.document_accountability import append_document_integrity_event
from app.services import (
    document_text_cache,
    matter_document_index,
    matter_fact_extraction,
    matter_form_reading,
)
from app.services.durable_jobs import enqueue_job
from app.services.matter_document_organization import (
    DocumentOrganizationError,
    get_folder_or_404,
    storage_routing_for_folder,
    tags_for_documents,
)
from app.services import matter_document_cloud_edit as cloud_edit
from app.services.matter_file_store import (
    MatterFileIntegrityError,
    MatterFileNotFound,
    MatterFileReadError,
    MatterFileStore,
)
from app.services.matter_document_revisions import (
    DocumentRevisionServiceError,
    assert_assistant_derivative_category_preserved,
    assert_document_not_in_revision_lineage,
    assert_no_legacy_assistant_derivative_release,
)
from app.services.graph_client import graph_request
from app.services.google_client import google_request
from app.services.provider_http import (
    ProviderAuthError,
    ProviderError,
    ProviderNotFound,
    ProviderThrottled,
)
from app.services import google_service_account
from app.services.token_vault import get_fresh_token

settings = get_settings()
router = APIRouter(prefix="/api", tags=["matter-documents"])
matter_file_store = MatterFileStore()


async def _get_matter_or_404(
    matter_id: str, tenant_id: uuid.UUID, db: AsyncSession
) -> Matter:
    """Fetch a matter ensuring it belongs to the current tenant."""
    result = await db.execute(
        select(Matter).where(
            Matter.id == matter_id,
            Matter.tenant_id == tenant_id,
        )
    )
    matter = result.scalar_one_or_none()
    if matter is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    return matter


async def _get_doc_or_404(
    doc_id: str, matter_id: str, tenant_id: uuid.UUID, db: AsyncSession
) -> MatterDocument:
    result = await db.execute(
        select(MatterDocument).where(
            MatterDocument.id == doc_id,
            MatterDocument.matter_id == matter_id,
            MatterDocument.tenant_id == tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _first_doc_attr(doc: MatterDocument, names: tuple[str, ...]) -> str | None:
    for name in names:
        value = getattr(doc, name, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _normalize_storage_provider(provider: str | None) -> str | None:
    if not provider:
        return None
    normalized = provider.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "google": "google_drive",
        "gdrive": "google_drive",
        "drive": "google_drive",
        "microsoft_graph": "onedrive",
        "ms_graph": "onedrive",
        "msgraph": "onedrive",
        "one_drive": "onedrive",
        "local_disk": "local",
        "disk": "local",
        "filesystem": "local",
    }
    return aliases.get(normalized, normalized)


def _doc_storage_provider(doc: MatterDocument) -> str | None:
    return _normalize_storage_provider(
        _first_doc_attr(
            doc,
            (
                "storage_provider",
                "provider",
                "provider_backend",
                "cloud_provider",
                "storage_backend",
            ),
        )
    )


def _doc_provider_object_id(doc: MatterDocument) -> str | None:
    return _first_doc_attr(
        doc,
        (
            "provider_object_id",
            "provider_item_id",
            "cloud_object_id",
            "cloud_file_id",
        ),
    )


def _doc_provider_drive_id(doc: MatterDocument) -> str | None:
    return _first_doc_attr(doc, ("provider_drive_id", "drive_id", "cloud_drive_id"))


def _storage_result_document_fields(storage_result) -> dict:
    return {
        "storage_path": storage_result.storage_path,
        "storage_provider": storage_result.provider,
        "storage_backend": storage_result.backend,
        "provider_object_id": storage_result.provider_item_id,
        "provider_drive_id": storage_result.drive_id,
        "provider_parent_id": storage_result.parent_id,
        "storage_error": storage_result.error,
    }


def organization_http_error(exc: DocumentOrganizationError) -> HTTPException:
    """Translate a folder/tag service error into the router's error shape."""
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


async def serialize_documents(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    documents: list[MatterDocument],
) -> list[MatterDocumentResponse]:
    """Attach folder paths and tags without an N+1 query per document."""
    if not documents:
        return []

    folder_ids = {doc.folder_id for doc in documents if doc.folder_id}
    folder_paths: dict[uuid.UUID, str] = {}
    if folder_ids:
        result = await db.execute(
            select(MatterDocumentFolder.id, MatterDocumentFolder.path).where(
                MatterDocumentFolder.tenant_id == tenant_id,
                MatterDocumentFolder.id.in_(folder_ids),
            )
        )
        folder_paths = {row[0]: row[1] for row in result.all()}

    tags_by_document = await tags_for_documents(
        db, tenant_id=tenant_id, document_ids=[doc.id for doc in documents]
    )

    # Access a signing packet grants is per-recipient and cannot be read off
    # ``portal_visible``; without this the tab calls a document the client is
    # signing "Private".
    signing_grants = await matter_signing_grant_document_ids(
        db,
        tenant_id=tenant_id,
        matter_ids={doc.matter_id for doc in documents},
    )

    editor_ids = {
        doc.external_edit_started_by
        for doc in documents
        if doc.external_edit_started_by is not None
    }
    editor_names: dict[uuid.UUID, str] = {}
    if editor_ids:
        result = await db.execute(
            select(User.id, User.full_name, User.email).where(
                User.tenant_id == tenant_id, User.id.in_(editor_ids)
            )
        )
        editor_names = {row[0]: row[1] or row[2] for row in result.all()}

    responses = []
    for doc in documents:
        response = MatterDocumentResponse.model_validate(doc)
        if doc.external_edit_started_by is not None:
            response.external_edit_started_by_name = editor_names.get(
                doc.external_edit_started_by
            )
        response.signing_access = (
            not doc.portal_visible
            and doc.uploaded_by_user_id is not None
            and doc.id in signing_grants
        )
        response.folder_path = (
            folder_paths.get(doc.folder_id) if doc.folder_id else None
        )
        response.tags = [
            MatterDocumentTagResponse.model_validate(tag)
            for tag in tags_by_document.get(doc.id, [])
        ]
        responses.append(response)
    return responses


async def serialize_document(
    db: AsyncSession, *, tenant_id: uuid.UUID, document: MatterDocument
) -> MatterDocumentResponse:
    return (await serialize_documents(db, tenant_id=tenant_id, documents=[document]))[0]


def _cloud_token_provider(storage_provider: str) -> str:
    if storage_provider == "google_drive":
        return "google"
    return "microsoft"


async def _delete_cloud_provider_object(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    storage_provider: str,
    object_id: str,
    drive_id: str | None,
) -> None:
    """Router-local storage delete shim until this moves into a storage service."""
    token_provider = _cloud_token_provider(storage_provider)
    token = await get_fresh_token(db, str(tenant_id), token_provider)
    if token_provider == "google":
        token = await google_service_account.prefer_service_account(
            db, str(tenant_id), token
        )
    if not token:
        raise ProviderAuthError(f"No connected token for {storage_provider}")

    safe_object_id = quote(object_id, safe="")
    safe_drive_id = quote(drive_id, safe="") if drive_id else None

    if storage_provider == "google_drive":
        await google_request(
            "DELETE",
            f"/{safe_object_id}",
            token=token,
            base_url="https://www.googleapis.com/drive/v3/files",
            provider_name="Google Drive",
        )
        return

    if storage_provider == "sharepoint":
        if not safe_drive_id:
            raise ProviderError("SharePoint document delete requires provider_drive_id")
        await graph_request(
            "DELETE",
            f"/drives/{safe_drive_id}/items/{safe_object_id}",
            token=token,
        )
        return

    if storage_provider == "onedrive":
        url = (
            f"/drives/{safe_drive_id}/items/{safe_object_id}"
            if safe_drive_id
            else f"/me/drive/items/{safe_object_id}"
        )
        await graph_request(
            "DELETE",
            url,
            token=token,
        )
        return

    raise ProviderError(f"Unsupported storage provider: {storage_provider}")


async def _delete_cloud_backing_if_needed(
    doc: MatterDocument,
    db: AsyncSession,
) -> None:
    storage_path = doc.storage_path or ""
    has_legacy_cloud_url = storage_path.startswith(("http://", "https://"))
    storage_provider = _doc_storage_provider(doc)
    object_id = _doc_provider_object_id(doc)

    if storage_provider in (None, "local") and not has_legacy_cloud_url:
        return

    if not storage_provider or storage_provider == "cloud" or not object_id:
        raise HTTPException(
            status_code=501,
            detail=(
                "Cloud-backed document deletion requires durable provider metadata; "
                "the database record was not removed."
            ),
        )

    try:
        await _delete_cloud_provider_object(
            db=db,
            tenant_id=doc.tenant_id,
            storage_provider=storage_provider,
            object_id=object_id,
            drive_id=_doc_provider_drive_id(doc),
        )
    except ProviderNotFound:
        return
    except ProviderThrottled as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cloud provider throttled document deletion; "
                "database record was not removed."
            ),
            headers=(
                {"Retry-After": str(int(exc.retry_after))}
                if exc.retry_after is not None
                else None
            ),
        ) from exc
    except ProviderAuthError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Cloud provider credentials could not delete this document; "
                "database record was not removed."
            ),
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Cloud provider document deletion failed; "
                "database record was not removed."
            ),
        ) from exc


@router.get(
    "/matters/{matter_id}/documents",
    response_model=MatterDocumentListResponse,
)
async def list_matter_documents(
    matter_id: str,
    request: Request,
    folder_id: str | None = Query(
        None,
        description=(
            "Filter to one folder. Omit for every document in the matter; pass "
            "'root' for documents that are not filed in any folder."
        ),
    ),
    include_subfolders: bool = Query(False),
    q: str | None = Query(None, max_length=200),
    tag_ids: list[uuid.UUID] = Query(default_factory=list),
    sort: str = Query("created_at", pattern="^(created_at|filename|file_size)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List documents attached to a matter, optionally scoped to a folder."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    await _get_matter_or_404(matter_id, user.tenant_id, db)

    stmt = select(MatterDocument).where(
        MatterDocument.matter_id == matter_id,
        MatterDocument.tenant_id == user.tenant_id,
    )

    requested_folder = (folder_id or "").strip()
    if requested_folder.lower() == "root":
        stmt = stmt.where(MatterDocument.folder_id.is_(None))
    elif requested_folder:
        try:
            folder_uuid = uuid.UUID(requested_folder)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="folder_id must be a UUID or 'root'"
            ) from exc
        try:
            folder = await get_folder_or_404(
                db,
                tenant_id=user.tenant_id,
                matter_id=uuid.UUID(matter_id),
                folder_id=folder_uuid,
            )
        except DocumentOrganizationError as exc:
            raise organization_http_error(exc) from exc
        if include_subfolders:
            subtree = select(MatterDocumentFolder.id).where(
                MatterDocumentFolder.tenant_id == user.tenant_id,
                MatterDocumentFolder.matter_id == folder.matter_id,
                or_(
                    MatterDocumentFolder.id == folder.id,
                    MatterDocumentFolder.path.startswith(f"{folder.path}/"),
                ),
            )
            stmt = stmt.where(MatterDocument.folder_id.in_(subtree))
        else:
            stmt = stmt.where(MatterDocument.folder_id == folder.id)

    search = (q or "").strip()
    if search:
        # ``\`` is the default LIKE escape in Postgres, so neutralize it first.
        pattern = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(
            or_(
                MatterDocument.filename.ilike(f"%{pattern}%"),
                MatterDocument.description.ilike(f"%{pattern}%"),
            )
        )

    for tag_id in dict.fromkeys(tag_ids):
        # One EXISTS per tag makes the filter conjunctive: a document must
        # carry every requested tag, not merely one of them.
        stmt = stmt.where(
            select(MatterDocumentTagLink.tag_id)
            .where(
                MatterDocumentTagLink.tenant_id == user.tenant_id,
                MatterDocumentTagLink.document_id == MatterDocument.id,
                MatterDocumentTagLink.tag_id == tag_id,
            )
            .exists()
        )

    sort_columns = {
        "created_at": MatterDocument.created_at,
        "filename": func.lower(MatterDocument.filename),
        "file_size": MatterDocument.file_size,
    }
    sort_column = sort_columns[sort]
    stmt = stmt.order_by(
        sort_column.asc() if order == "asc" else sort_column.desc(),
        # A stable tiebreaker keeps paging and test assertions deterministic
        # when several documents share a name, size, or timestamp.
        MatterDocument.id.asc(),
    )

    result = await db.execute(stmt)
    docs = list(result.scalars().all())
    return MatterDocumentListResponse(
        items=await serialize_documents(db, tenant_id=user.tenant_id, documents=docs),
        total=len(docs),
    )


@router.post(
    "/matters/{matter_id}/documents/upload",
    response_model=MatterDocumentResponse,
    status_code=201,
)
async def upload_matter_document(
    matter_id: str,
    request: Request,
    file: UploadFile = File(...),
    description: str | None = Form(None),
    document_category: str | None = Form(None),
    folder_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file attachment to a matter."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    matter = await _get_matter_or_404(matter_id, user.tenant_id, db)

    folder: MatterDocumentFolder | None = None
    if (folder_id or "").strip():
        try:
            folder = await get_folder_or_404(
                db,
                tenant_id=user.tenant_id,
                matter_id=uuid.UUID(matter_id),
                folder_id=uuid.UUID(folder_id.strip()),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="folder_id must be a UUID"
            ) from exc
        except DocumentOrganizationError as exc:
            raise organization_http_error(exc) from exc

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    reject_oversized_request(request, max_bytes, settings.MAX_FILE_SIZE_MB)
    file_bytes = await file.read()
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB}MB",
        )

    # Load tenant cloud preference
    ts_result = await db.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == user.tenant_id)
    )
    ts = ts_result.scalar_one_or_none()
    preferred_provider = ts.primary_cloud_provider if ts else None

    doc_id = uuid.uuid4()
    safe_filename = os.path.basename(file.filename)
    category_override, folder_segments = storage_routing_for_folder(folder)
    storage_result = await matter_file_store.store_matter_file_result(
        db=db,
        tenant_id=str(user.tenant_id),
        matter_slug=matter.slug,
        category=category_override or document_category or "general",
        filename=safe_filename,
        content=file_bytes,
        content_type=file.content_type or "application/octet-stream",
        matter_cloud_folder=matter.cloud_folder,
        preferred_provider=preferred_provider,
        folder_path=folder_segments,
    )

    doc = MatterDocument(
        id=doc_id,
        tenant_id=user.tenant_id,
        matter_id=uuid.UUID(matter_id),
        uploaded_by_user_id=user.id,
        folder_id=folder.id if folder else None,
        filename=safe_filename,
        content_type=file.content_type,
        file_size=len(file_bytes),
        **_storage_result_document_fields(storage_result),
        description=description,
        document_category=document_category,
    )
    db.add(doc)
    await db.flush()
    # Opt-in per firm. When on, a filled intake form is read for record values
    # in the background and a review task is raised; the upload itself never
    # waits on extraction, and extraction never writes a record directly.
    if matter_fact_extraction.extraction_enabled(ts):
        await enqueue_job(
            db,
            tenant_id=user.tenant_id,
            kind="matter_fact_extraction",
            idempotency_key=f"matter-facts:{doc.id}",
            payload={"matter_id": str(matter.id), "document_id": str(doc.id)},
        )
    await db.commit()
    await db.refresh(doc)
    return await serialize_document(db, tenant_id=user.tenant_id, document=doc)


@router.patch(
    "/matters/{matter_id}/documents/{doc_id}",
    response_model=MatterDocumentResponse,
)
async def update_matter_document(
    matter_id: str,
    doc_id: str,
    body: MatterDocumentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update description or category of an attached document."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    doc = await _get_doc_or_404(doc_id, matter_id, user.tenant_id, db)

    if body.description is not None:
        doc.description = body.description
    if body.document_category is not None:
        try:
            await assert_assistant_derivative_category_preserved(
                db,
                tenant_id=user.tenant_id,
                matter_id=uuid.UUID(matter_id),
                document_id=doc.id,
                requested_category=body.document_category,
            )
        except DocumentRevisionServiceError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        doc.document_category = body.document_category
    announce = False
    if body.portal_visible is not None:
        if body.portal_visible:
            try:
                await assert_no_legacy_assistant_derivative_release(
                    db,
                    tenant_id=user.tenant_id,
                    matter_id=uuid.UUID(matter_id),
                    document_id=doc.id,
                )
            except DocumentRevisionServiceError as exc:
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={"code": exc.code, "message": exc.message},
                ) from exc
        # Sharing used to be silent: the bit flipped and the client was never
        # told. Announce the first share only -- portal_shared_at is the record
        # that it happened, so toggling visibility off and on never re-announces
        # a document the client has already seen.
        announce = body.portal_visible and doc.portal_shared_at is None
        if announce:
            doc.portal_shared_at = datetime.now(timezone.utc)
        doc.portal_visible = body.portal_visible

    await db.commit()
    await db.refresh(doc)
    if announce:
        matter = await db.scalar(
            select(Matter).where(
                Matter.id == doc.matter_id, Matter.tenant_id == user.tenant_id
            )
        )
        if matter is not None and matter.portal_enabled:
            await notify_client_portal_update(
                db,
                tenant_id=user.tenant_id,
                actor_user_id=user.id,
                matter=matter,
                subject=f"A new document is available on {matter.matter_name or 'your matter'}",
                headline=shared_document_headline(matter, doc.filename),
                details=[("Document", doc.filename)],
                portal_tab="documents",
                action_label="View the document in your portal",
            )
    return await serialize_document(db, tenant_id=user.tenant_id, document=doc)


@router.delete("/matters/{matter_id}/documents/{doc_id}", status_code=204)
async def delete_matter_document(
    matter_id: str,
    doc_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete an attached document and its file from disk."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    doc = await _get_doc_or_404(doc_id, matter_id, user.tenant_id, db)
    await db.refresh(doc, with_for_update=True)

    try:
        await assert_document_not_in_revision_lineage(
            db,
            tenant_id=user.tenant_id,
            matter_id=uuid.UUID(matter_id),
            document_id=doc.id,
        )
    except DocumentRevisionServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    await _delete_cloud_backing_if_needed(doc, db)

    if doc.storage_path and os.path.exists(doc.storage_path):
        try:
            os.remove(doc.storage_path)
            parent_dir = os.path.dirname(doc.storage_path)
            if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
                os.rmdir(parent_dir)
        except OSError:
            pass

    # The cached text is the document's own words; it goes when the tenant's
    # last document with these bytes goes. Search rows cascade with the row.
    deleted_id, deleted_digest = doc.id, doc.document_sha256
    await db.delete(doc)
    await document_text_cache.forget_if_unreferenced(
        db,
        tenant_id=user.tenant_id,
        document_sha256=deleted_digest,
        except_document_id=deleted_id,
    )
    await db.commit()


@router.get("/matters/{matter_id}/documents/{doc_id}/open")
async def open_matter_document(
    matter_id: str,
    doc_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Resolve a fresh tenant-provider editing URL from durable object IDs."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    doc = await _get_doc_or_404(doc_id, matter_id, user.tenant_id, db)
    try:
        url = await matter_file_store.get_matter_file_open_url(
            db=db,
            tenant_id=str(user.tenant_id),
            document=doc,
        )
    except MatterFileNotFound as exc:
        raise HTTPException(status_code=404, detail="Cloud document not found") from exc
    except (MatterFileReadError, ProviderError) as exc:
        raise HTTPException(
            status_code=409,
            detail="The cloud document cannot be opened until its binding is repaired",
        ) from exc
    return RedirectResponse(
        url,
        status_code=307,
        headers={"Cache-Control": "no-store"},
    )


async def _lock_doc_or_404(
    doc_id: str, matter_id: str, tenant_id: uuid.UUID, db: AsyncSession
) -> MatterDocument:
    """Load a document row for update so two adoptions cannot interleave."""
    result = await db.execute(
        select(MatterDocument)
        .where(
            MatterDocument.id == doc_id,
            MatterDocument.matter_id == matter_id,
            MatterDocument.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _require_firm_staff(user) -> None:
    """Opening, bringing back or replacing a matter document is staff work.

    A client-portal login is a real ``User`` (``role="client"``) whose token
    ``get_current_user`` accepts, and portal responses expose shared document
    IDs. Refuse it before any database or provider access so a client can
    never overwrite a firm document.
    """
    if (getattr(user, "role", "") or "").strip().lower() == "client":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "staff_only",
                "message": "Only firm staff can edit matter documents.",
            },
        )


def _cloud_edit_http_error(exc: cloud_edit.CloudEditError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _provider_http_error(exc: Exception) -> HTTPException:
    """Plain-language errors for a provider read or write in the edit flow."""
    if isinstance(exc, MatterFileNotFound):
        return HTTPException(
            status_code=404,
            detail={
                "code": "cloud_file_missing",
                "message": "The file is no longer in the firm's cloud storage.",
            },
        )
    if isinstance(exc, ProviderAuthError):
        return HTTPException(
            status_code=409,
            detail={
                "code": "reconnect_required",
                "message": "The firm's Microsoft 365 or Google connection needs to be "
                "reconnected before LawHand can reach this file.",
            },
        )
    return HTTPException(
        status_code=503,
        detail={
            "code": "cloud_unavailable",
            "message": "The firm's cloud storage did not respond. Try again shortly.",
        },
    )


async def _refresh_index_after_adoption(
    tenant_id: uuid.UUID, document: MatterDocument, outcome: str
) -> None:
    if outcome == "adopted":
        await matter_document_index.enqueue_index(
            tenant_id=tenant_id,
            document_id=document.id,
            document_sha256=document.document_sha256,
        )


@router.post(
    "/matters/{matter_id}/documents/{doc_id}/cloud-edit",
    response_model=MatterDocumentCloudEditResponse,
)
async def start_matter_document_cloud_edit(
    matter_id: str,
    doc_id: str,
    body: MatterDocumentCloudEditRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return fresh links to open this Word document in the firm's office suite.

    Records who opened it, where and when, for the Documents tab. It is not a
    lock: the office suite handles co-authoring, and bringing the edits back
    is hash-checked.
    """
    user = await get_current_user(request, db)
    _require_firm_staff(user)
    await set_tenant_context(db, str(user.tenant_id))
    doc = await _lock_doc_or_404(doc_id, matter_id, user.tenant_id, db)
    try:
        cloud_edit.assert_editable_in_office(doc, require_cloud=True)
        reason = await cloud_edit.locked_reason(db, doc)
        if reason:
            raise cloud_edit.CloudEditError(
                409,
                "document_locked",
                f"{reason} Open it read-only from the cloud instead.",
            )
    except cloud_edit.CloudEditError as exc:
        raise _cloud_edit_http_error(exc) from exc
    try:
        metadata = await matter_file_store.get_matter_file_metadata(
            db=db, tenant_id=str(user.tenant_id), document=doc
        )
    except (MatterFileReadError, ProviderError) as exc:
        raise _provider_http_error(exc) from exc
    links = cloud_edit.open_links(metadata)
    app = body.app or next(iter(links))
    if app not in links:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "app_unavailable",
                "message": "This file cannot be opened in that app.",
            },
        )
    try:
        cloud_edit.start_external_edit(doc, user_id=user.id, app=app)
    except cloud_edit.CloudEditError as exc:
        raise _cloud_edit_http_error(exc) from exc
    await db.commit()
    await db.refresh(doc)
    return MatterDocumentCloudEditResponse(
        document=await serialize_document(db, tenant_id=user.tenant_id, document=doc),
        links=links,
        app=app,
    )


@router.post(
    "/matters/{matter_id}/documents/{doc_id}/reconcile",
    response_model=MatterDocumentCloudEditResponse,
)
async def reconcile_matter_document(
    matter_id: str,
    doc_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Bring back edits made in Word or Google Docs as this document's next version.

    Reads the exact cloud file by its durable ID and adopts it in place when
    it changed. Approved, filed and signing-bound documents are never
    overwritten; a change to one of them leaves it in ``conflict`` with the
    reason.
    """
    user = await get_current_user(request, db)
    _require_firm_staff(user)
    await set_tenant_context(db, str(user.tenant_id))
    doc = await _lock_doc_or_404(doc_id, matter_id, user.tenant_id, db)
    tenant_id = user.tenant_id
    try:
        cloud_edit.assert_editable_in_office(doc, require_cloud=True)
    except cloud_edit.CloudEditError as exc:
        raise _cloud_edit_http_error(exc) from exc
    try:
        content = await matter_file_store.read_matter_file_bytes(
            db=db,
            tenant_id=str(tenant_id),
            document=doc,
            expected_sha256=None,
            expected_size=None,
            max_bytes=cloud_edit.MAX_REVISED_BYTES,
            enforce_persisted_size=False,
        )
    except (MatterFileReadError, ProviderError) as exc:
        raise _provider_http_error(exc) from exc
    try:
        metadata = await matter_file_store.get_matter_file_metadata(
            db=db, tenant_id=str(tenant_id), document=doc
        )
    except (MatterFileReadError, ProviderError):
        # Change markers are a convenience; the adopted bytes are what count.
        metadata = None
    try:
        result = await cloud_edit.adopt_document_bytes(
            db,
            document=doc,
            content=content,
            actor_user_id=user.id,
            source="cloud_reconcile",
            metadata=metadata,
        )
    except cloud_edit.CloudEditError as exc:
        raise _cloud_edit_http_error(exc) from exc
    if result.outcome == "adopted":
        await matter_document_index.forget_document(
            db, tenant_id=tenant_id, document_id=doc.id
        )
    await db.commit()
    await db.refresh(doc)
    await _refresh_index_after_adoption(tenant_id, doc, result.outcome)
    return MatterDocumentCloudEditResponse(
        document=await serialize_document(db, tenant_id=tenant_id, document=doc),
        outcome=result.outcome,
        message=result.message,
    )


@router.post(
    "/matters/{matter_id}/documents/{doc_id}/revised-version",
    response_model=MatterDocumentCloudEditResponse,
)
async def upload_revised_matter_document(
    matter_id: str,
    doc_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Replace a Word document's content with an uploaded revised version.

    The fallback when someone cannot use Word or Google Docs through the
    firm's connection. The file goes to the same cloud item (or local file),
    and is adopted exactly like edits brought back from the office suite. If
    the cloud copy changed since LawHand last saved it, nothing is written:
    those edits must be brought back first.
    """
    user = await get_current_user(request, db)
    _require_firm_staff(user)
    await set_tenant_context(db, str(user.tenant_id))
    max_bytes = cloud_edit.MAX_REVISED_BYTES
    reject_oversized_request(request, max_bytes, max_bytes // (1024 * 1024))
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "file_too_large",
                "message": f"The revised version is larger than {max_bytes // (1024 * 1024)} MB.",
            },
        )
    doc = await _lock_doc_or_404(doc_id, matter_id, user.tenant_id, db)
    tenant_id = user.tenant_id
    try:
        cloud_edit.assert_editable_in_office(doc, require_cloud=False)
        snapshot = cloud_edit.inspect_revised_docx(content, filename=doc.filename)
        reason = await cloud_edit.locked_reason(db, doc)
        if reason:
            raise cloud_edit.CloudEditError(409, "document_locked", reason)
    except cloud_edit.CloudEditError as exc:
        raise _cloud_edit_http_error(exc) from exc
    if snapshot.source_sha256 == doc.document_sha256:
        return MatterDocumentCloudEditResponse(
            document=await serialize_document(db, tenant_id=tenant_id, document=doc),
            outcome="unchanged",
            message="This file is identical to the current version.",
        )

    is_cloud = doc.storage_backend in cloud_edit.CLOUD_BACKENDS
    try:
        if is_cloud and doc.document_sha256:
            current = await matter_file_store.read_matter_file_bytes(
                db=db,
                tenant_id=str(tenant_id),
                document=doc,
                expected_sha256=None,
                expected_size=None,
                max_bytes=max_bytes,
                enforce_persisted_size=False,
            )
            if cloud_edit.sha256_hex(current) != doc.document_sha256:
                raise cloud_edit.CloudEditError(
                    409,
                    "changed_in_office",
                    "This document was changed in Word or Google Docs since LawHand "
                    "last saved it. Bring back those changes first, then upload your "
                    "revised version if it is still needed.",
                )
        # Guard the write with the eTag of the bytes just checked, not the
        # stored one: SharePoint changes eTags on metadata edits too, and a
        # stale value would refuse an upload for no reason.
        if_match = None
        if doc.storage_backend in {"onedrive", "sharepoint"}:
            try:
                fresh = await matter_file_store.get_matter_file_metadata(
                    db=db, tenant_id=str(tenant_id), document=doc
                )
                if_match = fresh.etag
            except (MatterFileReadError, ProviderError):
                if_match = None
        storage_result = await matter_file_store.replace_matter_file_content(
            db=db,
            tenant_id=str(tenant_id),
            document=doc,
            content=content,
            content_type=cloud_edit.DOCX_CONTENT_TYPE,
            if_match=if_match,
        )
    except cloud_edit.CloudEditError as exc:
        raise _cloud_edit_http_error(exc) from exc
    except MatterFileIntegrityError as exc:
        raise _cloud_edit_http_error(
            cloud_edit.CloudEditError(
                409,
                "changed_in_office",
                "This document changed in Word while the upload was running. "
                "Bring back those changes first.",
            )
        ) from exc
    except (MatterFileReadError, ProviderError) as exc:
        raise _provider_http_error(exc) from exc
    try:
        result = await cloud_edit.adopt_document_bytes(
            db,
            document=doc,
            content=content,
            actor_user_id=user.id,
            source="revised_upload",
            storage_result=storage_result if is_cloud else None,
        )
    except cloud_edit.CloudEditError as exc:
        raise _cloud_edit_http_error(exc) from exc
    if result.outcome == "adopted":
        await matter_document_index.forget_document(
            db, tenant_id=tenant_id, document_id=doc.id
        )
    await db.commit()
    await db.refresh(doc)
    await _refresh_index_after_adoption(tenant_id, doc, result.outcome)
    return MatterDocumentCloudEditResponse(
        document=await serialize_document(db, tenant_id=tenant_id, document=doc),
        outcome=result.outcome,
        message=result.message,
    )


@router.get("/matters/{matter_id}/documents/{doc_id}/download")
async def download_matter_document(
    matter_id: str,
    doc_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Download exact registered bytes without trusting a persisted display URL."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    doc = await _get_doc_or_404(doc_id, matter_id, user.tenant_id, db)

    if doc.storage_backend in {"onedrive", "sharepoint", "google_drive"}:
        if doc.storage_state == "conflict":
            raise HTTPException(
                status_code=409,
                detail="This cloud document must be reconciled before download",
            )
        expected_sha256 = (
            doc.document_sha256 if doc.storage_state == "verified" else None
        )
        try:
            content = await matter_file_store.read_matter_file_bytes(
                db=db,
                tenant_id=str(user.tenant_id),
                document=doc,
                expected_sha256=expected_sha256,
                expected_size=doc.file_size,
            )
        except MatterFileIntegrityError as exc:
            doc.storage_state = "conflict"
            doc.storage_error = (
                "Download verification failed; cloud reconciliation is required"
            )
            if doc.generated_artifact_id and doc.generated_artifact_revision_id:
                await append_document_integrity_event(
                    db,
                    tenant_id=user.tenant_id,
                    matter_id=doc.matter_id,
                    task_id=doc.task_id,
                    artifact_id=doc.generated_artifact_id,
                    artifact_revision_id=doc.generated_artifact_revision_id,
                    document_id=doc.id,
                    event_type="cloud_download_integrity_conflict",
                    actor_type="user",
                    actor_user_id=user.id,
                    content_sha256=doc.document_sha256,
                    provider_object_id=doc.provider_object_id,
                    provider_etag=doc.provider_etag,
                    provider_version_id=doc.provider_version_id,
                    metadata={"storage_backend": doc.storage_backend},
                )
            await db.commit()
            raise HTTPException(
                status_code=409,
                detail="The cloud document changed and must be reconciled",
            ) from exc
        except MatterFileNotFound as exc:
            raise HTTPException(
                status_code=404, detail="Cloud document not found"
            ) from exc
        except (MatterFileReadError, ProviderError) as exc:
            raise HTTPException(
                status_code=503,
                detail="The cloud document is temporarily unavailable",
            ) from exc
        return Response(
            content=content,
            media_type=doc.content_type or "application/octet-stream",
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{quote(doc.filename, safe='')}"
                ),
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    if not doc.storage_path or not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=doc.storage_path,
        filename=doc.filename,
        media_type=doc.content_type or "application/octet-stream",
    )


@router.post("/matters/{matter_id}/documents/{doc_id}/facts")
async def propose_matter_document_facts(
    matter_id: str,
    doc_id: str,
    request: Request,
    ai: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Propose record values the source document itself supports.

    Read-only against the records: every candidate is returned for review and
    nothing is written until a reviewer accepts a specific one. ``ai=true``
    adds a bounded model pass for scans and drifted labels; it is opt-in, metered,
    and fails soft to the deterministic result.
    """
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    await _get_doc_or_404(doc_id, matter_id, user.tenant_id, db)
    return await matter_fact_extraction.propose(
        db, user, uuid.UUID(matter_id), uuid.UUID(doc_id), use_ai=ai
    )


class FormReadRequest(BaseModel):
    template_id: uuid.UUID
    version_no: int | None = Field(default=None, ge=1)
    # Send the clips OCR could not read to the vision model (opt-in, metered).
    use_ai: bool = False


@router.get("/matters/{matter_id}/documents/search")
async def search_matter_document_text(
    matter_id: str,
    request: Request,
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(8, ge=1, le=25),
    db: AsyncSession = Depends(get_db),
):
    """Excerpts from this matter's documents that mention ``q``.

    Searches the matter-scoped index built from the extraction cache (text
    layer and OCR). Each hit points at one document a person can open; the
    snippet is the document's own words.
    """
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    await _get_matter_or_404(matter_id, user.tenant_id, db)
    results = await matter_document_index.search(
        db,
        tenant_id=user.tenant_id,
        matter_id=uuid.UUID(matter_id),
        query=q,
        limit=limit,
        embedder=matter_document_index.default_embedder(),
    )
    indexed = await matter_document_index.indexed_documents(
        db, tenant_id=user.tenant_id, matter_id=uuid.UUID(matter_id)
    )
    return {"query": q, "results": results, "indexed_documents": len(indexed)}


@router.get("/matters/{matter_id}/documents/{doc_id}/facts/form-sources")
async def list_matter_document_form_sources(
    matter_id: str,
    doc_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """The forms this matter has generated, so a scan can be read against one."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    await _get_doc_or_404(doc_id, matter_id, user.tenant_id, db)
    return {
        "sources": await matter_form_reading.form_sources(
            db, tenant_id=user.tenant_id, matter_id=uuid.UUID(matter_id)
        )
    }


@router.post("/matters/{matter_id}/documents/{doc_id}/facts/from-form")
async def read_matter_document_against_form(
    matter_id: str,
    doc_id: str,
    payload: FormReadRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Read a scanned, hand-filled copy field by field against its template.

    Same review shape as ``facts``: every reading is a candidate for a person
    to accept through ``facts/accept``; nothing is written here.
    """
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    await _get_doc_or_404(doc_id, matter_id, user.tenant_id, db)
    return await matter_form_reading.read_against_form(
        db,
        user,
        uuid.UUID(matter_id),
        uuid.UUID(doc_id),
        template_id=payload.template_id,
        version_no=payload.version_no,
        use_ai=payload.use_ai,
    )


@router.post("/matters/{matter_id}/documents/{doc_id}/facts/accept")
async def accept_matter_document_fact(
    matter_id: str,
    doc_id: str,
    payload: matter_fact_extraction.FactDecision,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Write one reviewed value after re-proving it against the live source."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    await _get_doc_or_404(doc_id, matter_id, user.tenant_id, db)
    return await matter_fact_extraction.accept(
        db, user, uuid.UUID(matter_id), uuid.UUID(doc_id), payload
    )
