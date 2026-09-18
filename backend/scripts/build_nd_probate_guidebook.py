#!/usr/bin/env python3
"""Ship the North Dakota probate forms in the global sample library.

The State Court Administrator publishes the informal-probate forms as one
fillable PDF (*Informal Administration of an Estate*, NDPC Forms 1–19) plus
a few companion forms. This script takes those files as downloaded from
ndcourts.gov and writes them into ``backend/seed/sample_templates`` with a
manifest entry each, so ``seed_sample_templates.py`` loads them on deploy and
``app.services.probate.install`` copies them into a firm's own library.

What it changes in the PDF, and why:

* drops hyperlink annotations, the tagged-structure tree, outlines and the
  document-info dictionary — the template engine refuses ``/URI`` actions and
  the structure tree keeps them reachable even after the links are removed;
* clears the required bit on every field (a required box a form does not use
  would block generation; the court's PDF marks none, but a re-issue might);
* sets the multiline flag on the heirs-table and inventory fields so a filled
  value wraps instead of overflowing the box;
* leaves every page and every field in place — the packet is generated whole
  and the Probate tab tells staff which pages to print.

The field map in ``app.services.probate.forms.GUIDEBOOK_BINDINGS`` is checked
against the discovered fields: a mapped name the PDF no longer has, or a
binding the catalogue does not know, stops the build.

Run:  python backend/scripts/build_nd_probate_guidebook.py --source <guidebook.pdf>
      [--companion name=path ...] [--dry-run]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import os
import secrets
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = BACKEND_ROOT / "seed" / "sample_templates"

sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db"
)
os.environ.setdefault(
    "SECRET_KEY", "build-script-only-0000000000000000000000000000000000000000"
)
os.environ.setdefault(
    "TOKEN_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
)

from pypdf import PdfReader, PdfWriter  # noqa: E402
from pypdf.generic import ArrayObject, NameObject, NumberObject  # noqa: E402

from app.services.pdf_templates import discover_pdf_fields  # noqa: E402
from app.services.probate import forms as forms_module  # noqa: E402
from app.services.template_bindings import is_valid_binding  # noqa: E402
from scripts.build_library_intake_forms import update_manifest  # noqa: E402

SOURCE_NAME = "North Dakota Court System — Legal Self Help Center"
_ROOT_KEYS_TO_DROP = (
    "/OpenAction",
    "/AA",
    "/Names",
    "/StructTreeRoot",
    "/MarkInfo",
    "/Outlines",
    "/Metadata",
)
_REQUIRED_BIT = 1 << 1
_MULTILINE_BIT = 1 << 12

COMPANIONS: dict[str, tuple[str, str]] = {
    "nd-probate-declaration-of-service-mail": (
        "ND Probate — Declaration of Service by Mail",
        "Declaration of service by mail for probate filings (N.D.C.C. 30.1-03).",
    ),
    "nd-probate-declaration-of-service-personal": (
        "ND Probate — Declaration of Service by Personal Delivery",
        "Declaration of service by personal delivery for probate filings (N.D.C.C. 30.1-03).",
    ),
    "nd-probate-claim-against-estate": (
        "ND Probate — Claim Against Estate (with guide)",
        "Claim against estate form and the self-help guide it ships with (N.D.C.C. 30.1-19).",
    ),
    "nd-document-return-request": (
        "ND Document Return Request",
        "Clerk of court document return request; used to recover an original will.",
    ),
}


def _normalized_name(widget) -> str:
    from app.services.pdf_templates import _normalize_variable, _qualified_field_name

    return _normalize_variable(_qualified_field_name(widget) or "")


def clean(content: bytes, *, multiline: tuple[str, ...] = ()) -> bytes:
    """Return the PDF with active content removed and field flags adjusted."""

    reader = PdfReader(io.BytesIO(content), strict=False)
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        kept = ArrayObject()
        for ref in annots:
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Link":
                continue
            for key in ("/A", "/AA"):
                if key in obj:
                    del obj[NameObject(key)]
            if obj.get("/Subtype") == "/Widget":
                _adjust_flags(obj, multiline)
            kept.append(ref)
        page[NameObject("/Annots")] = kept
    root = writer._root_object
    for key in _ROOT_KEYS_TO_DROP:
        if key in root:
            del root[NameObject(key)]
    acroform = root.get("/AcroForm")
    if acroform is not None:
        acroform = acroform.get_object()
        acroform[NameObject("/NeedAppearances")] = _bool(True)
        for key in ("/XFA", "/AA"):
            if key in acroform:
                del acroform[NameObject(key)]
    writer._info = None
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _bool(value: bool):
    from pypdf.generic import BooleanObject

    return BooleanObject(value)


def _adjust_flags(widget, multiline: tuple[str, ...]) -> None:
    """Clear the required bit; set multiline where the map asks for it."""

    holder = widget
    if "/Ff" not in holder and "/Parent" in holder:
        holder = holder["/Parent"].get_object()
    flags = int(holder.get("/Ff", 0) or 0)
    flags &= ~_REQUIRED_BIT
    if _normalized_name(widget) in multiline:
        flags |= _MULTILINE_BIT
    holder[NameObject("/Ff")] = NumberObject(flags)


def _validate_guidebook(
    content: bytes,
) -> tuple[list[dict], dict[int, tuple[int, int]]]:
    fields = discover_pdf_fields(content)
    names = {field["name"] for field in fields}
    missing = sorted(set(forms_module.GUIDEBOOK_BINDINGS) - names)
    if missing:
        raise SystemExit(
            "Field map names fields the guidebook does not have: " + ", ".join(missing)
        )
    unknown = sorted(
        path
        for path in set(forms_module.GUIDEBOOK_BINDINGS.values())
        if not is_valid_binding(path)
    )
    if unknown:
        raise SystemExit("Unknown binding paths: " + ", ".join(unknown))
    required = sorted(field["name"] for field in fields if field.get("required"))
    if required:
        raise SystemExit("Required fields survived cleaning: " + ", ".join(required))
    ranges = forms_module.page_ranges(content)
    for item in forms_module.ND_PROBATE_FORMS:
        found = ranges.get(item.number)
        if found != item.pages:
            raise SystemExit(
                f"Form {item.number}: registry says pages {item.pages}, PDF says {found}"
            )
    return fields, ranges


def _entry(
    *,
    slug: str,
    title: str,
    description: str,
    content: bytes,
    field_count: int,
    bindings: dict[str, str],
    source_file: str,
    edition: str,
    extra: dict | None = None,
) -> dict:
    return {
        "category": "court_form",
        "description": description,
        "field_count": field_count,
        "filename": f"court_form/{slug}.pdf",
        "jurisdictions": ["North Dakota"],
        "origin": "court_form",
        "bindings": dict(sorted(bindings.items())),
        "provenance": {
            "source_name": SOURCE_NAME,
            "source_url": "https://www.ndcourts.gov/legal-self-help/informal-probate",
            "edition": edition,
            "retrieved_at": date.today().isoformat(),
            "source_files": [source_file],
        },
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "slug": slug,
        "title": title,
        **(extra or {}),
    }


def build_guidebook(source: Path, out_dir: Path, *, dry_run: bool) -> dict:
    content = clean(source.read_bytes(), multiline=forms_module.MULTILINE_FIELDS)
    fields, ranges = _validate_guidebook(content)
    bound = forms_module.iter_bound(fields)
    print(
        f"{source.name}: {len(fields)} fields, {len(bound)} bound, {len(content)} bytes"
    )
    for number, (first, last) in sorted(ranges.items()):
        print(f"  Form {number:>2}: pages {first}-{last}")
    if dry_run:
        for field in fields:
            binding = forms_module.GUIDEBOOK_BINDINGS.get(field["name"], "")
            print(f"  p{field.get('page')}: {field['name']}  ->  {binding}")
        return {}
    destination = out_dir / "court_form" / f"{forms_module.GUIDEBOOK_SLUG}.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return _entry(
        slug=forms_module.GUIDEBOOK_SLUG,
        title=forms_module.GUIDEBOOK_TITLE,
        description=(
            "The State Court Administrator's Informal Administration of an Estate "
            "packet: Forms 1–19 (small-estate affidavit, informal probate and "
            "appointment applications, statements, letters, notices, inventory, "
            "deeds, and closing statements) in one fillable PDF. Generate once from "
            "the estate record and print the pages the filing needs."
        ),
        content=content,
        field_count=len(fields),
        bindings=dict(bound),
        source_file=source.name,
        edition="Guidebook Rev. Aug 2025; forms Rev. Sep 2026",
        extra={"page_ranges": {str(k): list(v) for k, v in sorted(ranges.items())}},
    )


def build_companion(slug: str, source: Path, out_dir: Path, *, dry_run: bool) -> dict:
    title, description = COMPANIONS[slug]
    content = clean(source.read_bytes())
    fields = discover_pdf_fields(content)
    print(f"{source.name}: {len(fields)} fields, {len(content)} bytes -> {slug}")
    if dry_run:
        return {}
    destination = out_dir / "court_form" / f"{slug}.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return _entry(
        slug=slug,
        title=title,
        description=description,
        content=content,
        field_count=len(fields),
        bindings={},
        source_file=source.name,
        edition="Rev. 2024–2025",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="the guidebook PDF")
    parser.add_argument(
        "--companion",
        action="append",
        default=[],
        metavar="SLUG=PATH",
        help=f"a companion form; slugs: {', '.join(COMPANIONS)}",
    )
    parser.add_argument("--out", type=Path, default=SEED_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    entries = [build_guidebook(args.source, args.out, dry_run=args.dry_run)]
    for spec in args.companion:
        slug, _, path = spec.partition("=")
        if slug not in COMPANIONS or not path:
            raise SystemExit(f"Unknown companion: {spec}")
        entries.append(
            build_companion(slug, Path(path), args.out, dry_run=args.dry_run)
        )
    if args.dry_run:
        return 0
    total = update_manifest([entry for entry in entries if entry], args.out)
    print(f"Library manifest now lists {total} forms -> {args.out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
