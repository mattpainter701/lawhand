"""Global sample-template library router.

Read-only catalog of platform-owned starter templates available to every
authenticated tenant. Unlike ``/api/templates`` (tenant-owned, RLS-scoped),
this catalog is shared content: tenants may list, inspect, download, and render
samples, but cannot mutate them. Seeding is done by
``scripts/seed_sample_templates.py``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db, set_tenant_context
from app.middleware.tenant import get_current_user
from app.models.matter_document import MatterDocument
from app.models.plugin import MatterEvent
from app.models.sample_template import SampleTemplate
from app.models.tenant import TenantSettings
from app.schemas.sample_template import (
    SampleTemplateListResponse,
    SampleTemplateRenderRequest,
    SampleTemplateResponse,
    SampleTemplateSaveToMatterRequest,
    SampleTemplateSaveToMatterResponse,
    SampleTemplateSmartFillRequest,
    SampleTemplateSmartFillResponse,
)
from app.services.access_control import require_capability
from app.services.matter_document_organization import (
    DocumentOrganizationError,
    get_folder_or_404,
    storage_routing_for_folder,
)
from app.services.pdf_templates import TemplatePdfError, fill_pdf_template
from app.routers.document_templates import (
    _compensate_staged_document,
    _load_render_matter,
    _matter_document_commit_outcome,
    _rollback_quietly,
    _saved_document_response,
    _storage_document_fields,
    build_variable_suggestions,
    matter_file_store,
)

router = APIRouter(prefix="/api/templates/library", tags=["sample-templates"])
settings = get_settings()
logger = logging.getLogger(__name__)


def _seed_root() -> Path:
    if settings.SAMPLE_TEMPLATE_DIR:
        return Path(settings.SAMPLE_TEMPLATE_DIR).resolve()
    return (Path(__file__).resolve().parents[2] / "seed" / "sample_templates").resolve()


def _safe_generated_filename(title: str, extension: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", (title or "sample"))
    stem = stem.replace("..", ".").strip(" .")[:180] or "sample"
    return f"{stem}.{extension.lstrip('.')}"


async def _load_sample(db: AsyncSession, sample_id: uuid.UUID) -> SampleTemplate:
    sample = await db.scalar(
        select(SampleTemplate).where(
            SampleTemplate.id == sample_id,
            SampleTemplate.is_active.is_(True),
        )
    )
    if not sample:
        raise HTTPException(status_code=404, detail="Sample template not found")
    return sample


def _verified_source(sample: SampleTemplate) -> bytes:
    root = _seed_root()
    target = (root / sample.source_filename).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(
            status_code=409, detail="The sample template source is unavailable"
        )
    content = target.read_bytes()
    if hashlib.sha256(content).hexdigest() != sample.source_sha256:
        raise HTTPException(
            status_code=409, detail="The sample template failed its integrity check"
        )
    return content


@router.get("", response_model=SampleTemplateListResponse)
async def list_sample_templates(
    category: str | None = Query(None),
    jurisdiction: str | None = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = [SampleTemplate.is_active.is_(True)]
    if category:
        filters.append(SampleTemplate.category == category)

    result = await db.execute(select(SampleTemplate).where(*filters))
    samples = result.scalars().all()

    if jurisdiction:
        samples = [
            sample for sample in samples if jurisdiction in (sample.jurisdictions or [])
        ]

    count_stmt = select(func.count()).select_from(
        select(SampleTemplate).where(*filters).subquery()
    )
    total = (await db.execute(count_stmt)).scalar_one()

    return SampleTemplateListResponse(
        items=[SampleTemplateResponse.model_validate(s) for s in samples],
        total=total,
    )


@router.get("/{sample_id}", response_model=SampleTemplateResponse)
async def get_sample_template(
    sample_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sample = await _load_sample(db, sample_id)
    return SampleTemplateResponse.model_validate(sample)


@router.get("/{sample_id}/source")
async def download_sample_source(
    sample_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sample = await _load_sample(db, sample_id)
    content = await asyncio.to_thread(_verified_source, sample)
    filename = _safe_generated_filename(sample.title, "pdf")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
        },
    )


@router.post(
    "/{sample_id}/smart-fill-preview", response_model=SampleTemplateSmartFillResponse
)
async def smart_fill_sample_template(
    sample_id: uuid.UUID,
    payload: SampleTemplateSmartFillRequest,
    current_user=Depends(require_capability("manage_documents")),
    db: AsyncSession = Depends(get_db),
):
    """Suggest values from one tenant-scoped matter without saving anything."""
    await set_tenant_context(db, str(current_user.tenant_id))
    sample = await _load_sample(db, sample_id)
    if not sample.variable_schema:
        raise HTTPException(
            status_code=409,
            detail="The sample template has not been seeded with a field schema.",
        )
    template = SimpleNamespace(
        id=sample.id,
        tenant_id=current_user.tenant_id,
        variable_schema=sample.variable_schema,
    )
    resolved_matter_id, suggestions = await build_variable_suggestions(
        template=template,
        requested_variables=payload.variables,
        matter_id=payload.matter_id,
        tenant_id=uuid.UUID(str(current_user.tenant_id)),
        current_user=current_user,
        db=db,
    )
    return SampleTemplateSmartFillResponse(
        sample_id=str(sample.id),
        matter_id=resolved_matter_id,
        variables=[item.model_dump(mode="json") for item in suggestions],
    )


@router.post("/{sample_id}/render-file")
async def render_sample_template(
    sample_id: uuid.UUID,
    payload: SampleTemplateRenderRequest,
    current_user=Depends(require_capability("manage_documents")),
    db: AsyncSession = Depends(get_db),
):
    sample = await _load_sample(db, sample_id)
    if not sample.variable_schema:
        raise HTTPException(
            status_code=409,
            detail="The sample template has not been seeded with a field schema.",
        )
    content = await asyncio.to_thread(_verified_source, sample)
    try:
        output = await asyncio.to_thread(
            fill_pdf_template,
            content,
            variable_schema=sample.variable_schema,
            variables=payload.variables,
            flatten=True,
            enforce_required=False,
        )
    except TemplatePdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filename = _safe_generated_filename(sample.title, "pdf")
    return Response(
        content=output,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
        },
    )


@router.post(
    "/{sample_id}/save-to-matter",
    response_model=SampleTemplateSaveToMatterResponse,
    response_model_exclude_none=True,
    status_code=201,
)
async def save_sample_to_matter(
    sample_id: uuid.UUID,
    payload: SampleTemplateSaveToMatterRequest,
    current_user=Depends(require_capability("manage_documents")),
    db: AsyncSession = Depends(get_db),
):
    """Fill a global library form and file the PDF on one matter.

    The library form stays read-only shared content: nothing is copied into the
    firm's template library. Only the filled PDF lands on the matter, with the
    library form recorded as its source, so a one-off court form does not have
    to be imported, reviewed, tested and published as a firm template first.
    """
    tenant_id = uuid.UUID(str(current_user.tenant_id))
    await set_tenant_context(db, str(tenant_id))
    sample = await _load_sample(db, sample_id)
    if not sample.variable_schema:
        raise HTTPException(
            status_code=409,
            detail="The sample template has not been seeded with a field schema.",
        )
    matter = await _load_render_matter(
        db, tenant_id=tenant_id, matter_id=payload.matter_id
    )
    folder = None
    if payload.folder_id:
        try:
            folder = await get_folder_or_404(
                db,
                tenant_id=tenant_id,
                matter_id=matter.id,
                folder_id=payload.folder_id,
            )
        except DocumentOrganizationError as exc:
            raise HTTPException(exc.status_code, exc.message) from exc

    source = await asyncio.to_thread(_verified_source, sample)
    try:
        output = await asyncio.to_thread(
            fill_pdf_template,
            source,
            variable_schema=sample.variable_schema,
            variables=payload.variables,
            flatten=True,
            enforce_required=True,
        )
    except TemplatePdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    output_sha256 = hashlib.sha256(output).hexdigest()

    doc_id = uuid.uuid4()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_filename = _safe_generated_filename(
        f"{sample.title}-{timestamp}-{doc_id.hex[:8]}", "pdf"
    )
    tenant_settings = await db.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    folder_category, folder_path = storage_routing_for_folder(folder)
    storage_result = await matter_file_store.store_matter_file_result(
        db=db,
        tenant_id=str(tenant_id),
        matter_slug=matter.slug,
        category=folder_category or "generated",
        folder_path=folder_path,
        filename=output_filename,
        content=output,
        content_type="application/pdf",
        matter_cloud_folder=matter.cloud_folder,
        preferred_provider=(
            tenant_settings.primary_cloud_provider if tenant_settings else None
        ),
    )

    fields = [
        field
        for field in (sample.variable_schema or {}).get("fields", [])
        if isinstance(field, dict) and field.get("name")
    ]
    filled = sorted(name for name, value in payload.variables.items() if value)
    verified = sorted(
        name
        for name in set(payload.verified_fields)
        if str(payload.variables.get(name) or "").strip()
    )
    provenance = sample.provenance or {}
    doc = MatterDocument(
        id=doc_id,
        document_sha256=output_sha256,
        matter_id=matter.id,
        tenant_id=tenant_id,
        uploaded_by_user_id=current_user.id,
        filename=output_filename,
        content_type="application/pdf",
        file_size=len(output),
        description=f"Filled from global library form: {sample.title}",
        document_category="generated",
        folder_id=folder.id if folder else None,
        **_storage_document_fields(storage_result),
    )
    doc.generation_summary = {
        "sample_template_id": str(sample.id),
        "sample_template_title": sample.title,
        "source": "global_library",
        "total": len(fields),
        "filled": len(filled),
        "verified": len(verified),
        "verified_fields": verified,
    }
    event = MatterEvent(
        tenant_id=tenant_id,
        matter_id=matter.id,
        event_type="document_generated",
        title=f"Generated document: {output_filename}",
        content=f"Filled from global library form {sample.title}.",
        note_type="system",
        metadata_json={
            "sample_template_id": str(sample.id),
            "sample_template_title": sample.title,
            "sample_source_sha256": sample.source_sha256,
            "sample_source_name": provenance.get("source_name"),
            "sample_edition": provenance.get("edition"),
            "output_document_id": str(doc_id),
            "output_filename": output_filename,
            "output_format": "pdf",
            "output_sha256": output_sha256,
            "filled_variables": filled,
            "verified_fields": verified,
            "verified_count": len(verified),
            "flatten_pdf": True,
        },
        created_by=current_user.id,
    )
    db.add_all([doc, event])
    try:
        await db.flush()
    except Exception as exc:
        logger.exception(
            "Library form save flush failed tenant=%s matter=%s; removing staged file",
            tenant_id,
            matter.id,
        )
        await _rollback_quietly(db, tenant_id=tenant_id, matter_id=matter.id)
        cleaned = await _compensate_staged_document(
            db,
            tenant_id=str(tenant_id),
            matter_id=matter.id,
            storage_result=storage_result,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "The document could not be saved; the staged file was removed. Try again."
                if cleaned
                else "The document could not be saved and its staged file could not "
                "be removed. Contact support before retrying."
            ),
        ) from exc
    try:
        await db.commit()
        await db.refresh(doc)
    except Exception as exc:
        # A lost COMMIT acknowledgement is ambiguous: deleting the file before
        # confirming the row is absent could orphan a document that did commit.
        logger.error(
            "Library form save commit failed tenant=%s matter=%s document=%s",
            tenant_id,
            matter.id,
            doc_id,
            exc_info=True,
        )
        rolled_back = await _rollback_quietly(
            db, tenant_id=tenant_id, matter_id=matter.id
        )
        outcome = (
            await _matter_document_commit_outcome(
                tenant_id=tenant_id, document_id=doc_id
            )
            if rolled_back
            else None
        )
        if outcome is not True:
            if outcome is False:
                await _compensate_staged_document(
                    db,
                    tenant_id=str(tenant_id),
                    matter_id=matter.id,
                    storage_result=storage_result,
                )
            raise HTTPException(
                status_code=500,
                detail=(
                    "The document could not be saved. Check the matter's documents "
                    "before trying again."
                ),
            ) from exc
        await set_tenant_context(db, str(tenant_id))
        doc = await db.scalar(
            select(MatterDocument).where(
                MatterDocument.id == doc_id, MatterDocument.tenant_id == tenant_id
            )
        )

    return SampleTemplateSaveToMatterResponse(
        sample_id=str(sample.id),
        matter_id=str(matter.id),
        matter_document_id=str(doc_id),
        matter_document=(
            await _saved_document_response(db, tenant_id=tenant_id, document=doc)
            if doc is not None
            else None
        ),
        output_filename=output_filename,
        storage_backend=storage_result.backend,
        storage_warning=storage_result.error,
    )
