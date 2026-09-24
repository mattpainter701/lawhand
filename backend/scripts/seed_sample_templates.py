"""Seed the platform-owned sample-template catalog from the curated library.

Reads ``backend/seed/sample_templates/manifest.json`` and the PDFs it references,
derives each form's AcroForm field schema with ``discover_pdf_fields``, and
upserts rows into ``sample_templates`` keyed by ``slug``.

Idempotent: running it again refreshes existing rows (title, category,
jurisdictions, schema, and source hashes) without creating duplicates.

Usage (from backend/):
    python scripts/seed_sample_templates.py [--prune]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

# Register only the catalog table, not app.main: this runs as the deploy's
# one-shot migrator, where pulling in every router and service (and their
# LiteLLM/storage clients) would widen the startup surface for no reason.
from app.database import async_session_maker  # noqa: E402
from app.models.sample_template import SampleTemplate  # noqa: E402
from app.services.pdf_templates import TemplatePdfError, discover_pdf_fields  # noqa: E402
from app.services.template_bindings import is_valid_binding  # noqa: E402

SEED_DIR = Path(__file__).resolve().parents[1] / "seed" / "sample_templates"


_PROVENANCE_FIELDS = {
    "source_name",
    "source_url",
    "edition",
    "retrieved_at",
    "source_files",
}


def _provenance(form: dict) -> dict | None:
    """Validate the manifest's provenance block before it reaches the catalog.

    Provenance is what tells a user which of several same-titled forms they are
    about to file, so an unrecognised key is a build error rather than
    something to pass through unchecked. Absent provenance stays absent: the UI
    says the source was not recorded instead of implying one.
    """

    provenance = form.get("provenance")
    if provenance in (None, {}):
        return None
    if not isinstance(provenance, dict):
        raise SystemExit(f"Provenance must be an object: {form['slug']}")
    unknown = sorted(set(provenance) - _PROVENANCE_FIELDS)
    if unknown:
        raise SystemExit(
            f"Unknown provenance field in manifest for {form['slug']}: "
            f"{', '.join(unknown)}"
        )
    return provenance


def _variable_schema(
    content: bytes,
    bindings: dict | None = None,
    option_labels: dict | None = None,
) -> dict:
    """Derive the field schema from the PDF, carrying the manifest's curation.

    Field discovery stays the single source of truth for what is in the form.
    A manifest may additionally declare where a field's value comes from — the
    authored firm-paperwork samples name their fields after the platform's own
    variables, and curated court forms map their caption and signature block —
    and those declarations are attached here so Smart Fill resolves them
    without a firm re-declaring anything. ``option_labels`` gives a radio or
    choice option a readable label when the PDF only carries an export value
    such as "Choice 1"; the export value itself is unchanged, so filling writes
    exactly what the PDF expects.

    A path the catalogue does not recognise, or curation naming a field or
    option the PDF does not have, is a build error rather than a declaration
    that silently does nothing.
    """

    fields = discover_pdf_fields(content)
    by_name = {field["name"]: field for field in fields}
    declared = bindings or {}
    unknown = sorted(
        path for path in set(declared.values()) if not is_valid_binding(path)
    )
    if unknown:
        raise SystemExit(f"Unknown binding path in manifest: {', '.join(unknown)}")
    missing = sorted(set(declared) - set(by_name))
    if missing:
        raise SystemExit(f"Manifest binds unknown field: {', '.join(missing)}")
    for field in fields:
        binding = declared.get(field["name"])
        if binding:
            field["binding"] = binding
    for name, labels in (option_labels or {}).items():
        field = by_name.get(name)
        if field is None or field["field_type"] not in {"radio", "choice"}:
            raise SystemExit(f"Manifest labels options of a non-option field: {name}")
        values = [
            option["value"] if isinstance(option, dict) else option
            for option in field["options"]
        ]
        stray = sorted(set(labels) - set(values))
        if stray:
            raise SystemExit(
                f"Manifest labels unknown option(s) of {name}: {', '.join(stray)}"
            )
        field["options"] = [
            {"value": value, "label": labels.get(value, value)} for value in values
        ]
    return {
        "version": 1,
        "source": "sample_library",
        "fields": fields,
    }


async def seed(prune: bool = False) -> None:
    manifest = json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))
    forms = manifest.get("forms") or []
    if not forms:
        raise SystemExit("Sample template manifest is empty")

    async with async_session_maker() as db:
        existing = {
            slug: row
            for slug, row in (
                await db.execute(select(SampleTemplate.slug, SampleTemplate.id))
            ).all()
        }
        for form in forms:
            source = SEED_DIR / form["filename"]
            if not source.is_file():
                raise SystemExit(f"Sample source missing: {form['filename']}")
            content = source.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != form["sha256"]:
                raise SystemExit(
                    f"Sample source integrity mismatch: {form['filename']}"
                )
            try:
                schema = _variable_schema(
                    content, form.get("bindings"), form.get("option_labels")
                )
            except TemplatePdfError as exc:
                print(f"SKIP {form['slug']}: {exc}")
                continue
            values = {
                "slug": form["slug"],
                "title": form["title"],
                "category": form["category"],
                "jurisdictions": form.get("jurisdictions") or [],
                "description": form.get("description"),
                "format": "pdf",
                "source_filename": form["filename"],
                "source_sha256": digest,
                "source_file_size": len(content),
                "field_count": len(schema["fields"]),
                "variable_schema": schema,
                "provenance": _provenance(form),
                "is_active": True,
            }
            slug = form["slug"]
            if slug in existing:
                row = await db.scalar(
                    select(SampleTemplate).where(SampleTemplate.slug == slug)
                )
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                db.add(SampleTemplate(**values))
        if prune:
            kept = {form["slug"] for form in forms}
            stale = [
                row
                for row in (
                    await db.execute(select(SampleTemplate))
                ).scalars().all()
                if row.slug not in kept
            ]
            for row in stale:
                await db.delete(row)
        await db.commit()

    print(f"Seeded {len(forms)} sample templates into sample_templates")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete catalog rows that are no longer in the manifest",
    )
    args = parser.parse_args()
    asyncio.run(seed(prune=args.prune))


if __name__ == "__main__":
    main()
