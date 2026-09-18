"""Put the North Dakota probate forms into a firm's own template library.

The forms ship with the platform (``backend/seed/sample_templates``) and are
seeded into the shared sample catalogue on every deploy. A firm generates from
its *own* templates, so this installer copies each probate sample into the
tenant's ``document_templates`` as a draft. It is idempotent: a second run
finds the first copy by its sample slug and creates nothing.

Nothing here publishes. A copied form stays a draft until someone with the
right to approve templates activates it in Template Studio, exactly as an
uploaded form would.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import sample_import
from app.services.probate import forms as forms_module

MODULE = "trust-estate"
JURISDICTION = "North Dakota"


async def install_forms_pack(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> dict[str, Any]:
    installed: list[dict[str, Any]] = []
    missing: list[str] = []
    for slug, kind, description in forms_module.PACK_SAMPLES:
        sample = await sample_import.find_sample(db, slug)
        if sample is None:
            missing.append(slug)
            continue
        try:
            template, created = await sample_import.import_sample_as_template(
                db,
                tenant_id,
                sample,
                module=MODULE,
                kind=kind,
                jurisdiction=JURISDICTION,
                description=description,
            )
        except sample_import.SampleSourceError:
            missing.append(slug)
            continue
        installed.append(
            {
                "slug": slug,
                "template_id": str(template.id),
                "title": template.title,
                "created": created,
                "status": template.status,
                "published": bool(template.is_active),
            }
        )
    await db.commit()
    return {"templates": installed, "missing_samples": missing}
