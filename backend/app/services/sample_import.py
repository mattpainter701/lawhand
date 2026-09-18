"""Copy a platform sample form into a firm's own template library.

The sample library is read-only and shared by every tenant. A firm generates
from its *own* templates, so a court form the platform ships has to be copied
into ``document_templates`` first, bytes and field schema intact, before the
studio's activation and generation gates can apply to it. Until this module
the only way a PDF became a tenant template was an upload.

The copy is a draft: inactive, unpublished, and provenance-stamped with the
sample slug so a second import finds the first instead of duplicating it.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.document_template import DocumentTemplate
from app.models.sample_template import SampleTemplate


class SampleSourceError(RuntimeError):
    """The sample's shipped bytes are missing or fail their integrity check."""


def seed_root() -> Path:
    settings = get_settings()
    if settings.SAMPLE_TEMPLATE_DIR:
        return Path(settings.SAMPLE_TEMPLATE_DIR).resolve()
    return (Path(__file__).resolve().parents[2] / "seed" / "sample_templates").resolve()


def verified_source(sample: SampleTemplate) -> bytes:
    root = seed_root()
    target = (root / sample.source_filename).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise SampleSourceError("The sample template source is unavailable")
    content = target.read_bytes()
    if hashlib.sha256(content).hexdigest() != sample.source_sha256:
        raise SampleSourceError("The sample template failed its integrity check")
    return content


async def find_sample(db: AsyncSession, slug: str) -> SampleTemplate | None:
    return await db.scalar(
        select(SampleTemplate).where(
            SampleTemplate.slug == slug, SampleTemplate.is_active.is_(True)
        )
    )


async def find_import(
    db: AsyncSession, tenant_id: uuid.UUID, slug: str
) -> DocumentTemplate | None:
    """The tenant's template previously imported from ``slug``, if any."""

    rows = (
        await db.execute(
            select(DocumentTemplate).where(
                DocumentTemplate.tenant_id == tenant_id,
                DocumentTemplate.source_provenance.isnot(None),
            )
        )
    ).scalars()
    for row in rows:
        provenance = row.source_provenance or {}
        if isinstance(provenance, dict) and provenance.get("sample_slug") == slug:
            return row
    return None


async def import_sample_as_template(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    sample: SampleTemplate,
    *,
    module: str | None = None,
    kind: str | None = None,
    jurisdiction: str | None = None,
    description: str | None = None,
    visibility: str = "tenant",
) -> tuple[DocumentTemplate, bool]:
    """Return the tenant's copy of ``sample`` and whether it was just created."""

    existing = await find_import(db, tenant_id, sample.slug)
    if existing is not None:
        return existing, False
    # Imported lazily: the router module owns the on-disk layout for template
    # sources, and importing it at module load would pull the whole router in.
    from app.routers.document_templates import _persist_template_source

    content = verified_source(sample)
    template_id = uuid.uuid4()
    source_path = await _persist_template_source(
        tenant_id=str(tenant_id),
        template_id=template_id,
        filename=Path(sample.source_filename).name,
        content=content,
    )
    schema: dict[str, Any] = dict(
        sample.variable_schema or {"version": 1, "fields": []}
    )
    schema = {**schema, "source": "sample_import", "sample_slug": sample.slug}
    provenance: dict[str, Any] = {"sample_slug": sample.slug}
    if isinstance(sample.provenance, dict):
        provenance.update(sample.provenance)
    template = DocumentTemplate(
        id=template_id,
        tenant_id=tenant_id,
        title=sample.title,
        body="",
        category=sample.category,
        description=description or sample.description,
        visibility=visibility,
        status="draft",
        format="pdf",
        module=module,
        jurisdiction=jurisdiction
        or ((sample.jurisdictions or [None])[0] if sample.jurisdictions else None),
        kind=kind,
        variable_schema=schema,
        source_storage_path=source_path,
        source_filename=Path(sample.source_filename).name,
        source_content_type="application/pdf",
        source_sha256=sample.source_sha256,
        source_file_size=len(content),
        source_provenance=provenance,
        is_active=False,
    )
    db.add(template)
    await db.flush()
    return template, True
