"""The shipped North Dakota probate packet and its field map stay in step.

The guidebook is committed as one PDF; this test is what keeps a re-issued
edition from silently breaking generation: every mapped field must still be
in the PDF, every binding must be one the catalogue knows, and the page each
form starts on must match the registry the Probate tab prints from.
"""

import hashlib
import io
import json
from pathlib import Path

from pypdf import PdfReader

from app.services.pdf_templates import MAX_PDF_WIDGETS, discover_pdf_fields
from app.services.probate import forms
from app.services.template_bindings import is_valid_binding

SEED_DIR = Path(__file__).resolve().parents[1] / "seed" / "sample_templates"


def _manifest_entry(slug: str) -> dict:
    manifest = json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))
    return next(form for form in manifest["forms"] if form["slug"] == slug)


def _guidebook() -> tuple[dict, bytes]:
    entry = _manifest_entry(forms.GUIDEBOOK_SLUG)
    content = (SEED_DIR / entry["filename"]).read_bytes()
    return entry, content


def test_the_guidebook_ships_whole_and_matches_its_manifest_entry():
    entry, content = _guidebook()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert entry["size_bytes"] == len(content)
    assert entry["origin"] == "court_form"
    assert entry["jurisdictions"] == ["North Dakota"]
    assert entry["provenance"]["source_name"].startswith("North Dakota Court System")
    reader = PdfReader(io.BytesIO(content), strict=False)
    assert len(reader.pages) == 63
    assert not reader.metadata


def test_every_field_is_discoverable_within_the_raised_cap():
    entry, content = _guidebook()
    fields = discover_pdf_fields(content)
    assert 200 < len(fields) <= MAX_PDF_WIDGETS
    assert len(fields) == entry["field_count"]
    assert not any(field.get("required") for field in fields)


def test_the_field_map_names_real_fields_and_known_bindings():
    entry, content = _guidebook()
    names = {field["name"] for field in discover_pdf_fields(content)}
    assert set(forms.GUIDEBOOK_BINDINGS) <= names
    assert all(is_valid_binding(path) for path in forms.GUIDEBOOK_BINDINGS.values())
    assert entry["bindings"] == dict(sorted(forms.GUIDEBOOK_BINDINGS.items()))
    # Every form's caption trio is bound, so a generated packet is captioned
    # on every page a clerk receives.
    for court, estate, case in forms._CAPTION.values():
        assert forms.GUIDEBOOK_BINDINGS[court] == "estate.venue_county"
        assert forms.GUIDEBOOK_BINDINGS[estate] == "estate.decedent_name"
        assert forms.GUIDEBOOK_BINDINGS[case] == "estate.case_number"


def test_the_heirs_table_fields_accept_several_lines():
    _, content = _guidebook()
    multiline = {
        field["name"]
        for field in discover_pdf_fields(content)
        if field.get("multiline")
    }
    assert set(forms.MULTILINE_FIELDS) <= multiline


def test_page_ranges_come_from_the_pdf_and_match_the_registry():
    entry, content = _guidebook()
    ranges = forms.page_ranges(content)
    assert set(ranges) == {item.number for item in forms.ND_PROBATE_FORMS}
    for item in forms.ND_PROBATE_FORMS:
        assert ranges[item.number] == item.pages, item.number
        assert entry["page_ranges"][str(item.number)] == list(item.pages)
    # Forms appear in numerical order and never overlap.
    ordered = [ranges[number] for number in sorted(ranges)]
    assert all(a[1] < b[0] for a, b in zip(ordered, ordered[1:]))


def test_forms_for_each_track_are_the_statutory_filing_sets():
    assert [f.number for f in forms.forms_for("informal_testate")] == [2, 3, 4, 5, 7]
    assert [f.number for f in forms.forms_for("informal_intestate")] == [
        5,
        7,
        17,
        18,
        19,
    ]
    assert [f.number for f in forms.forms_for("small_estate_affidavit")] == [1]
    assert forms.forms_for("formal_testate_late") == ()
    assert forms.forms_for(None) == ()
    assert forms.form(2).title.startswith("Application for Informal Probate")
    assert forms.form(99) is None


def test_the_formal_checklist_names_the_pleadings_the_firm_supplies():
    testate = forms.formal_checklist("formal_testate_late")
    intestate = forms.formal_checklist("formal_intestate_late")
    assert [item["slot"] for item in testate] == [
        "petition",
        "notice_of_hearing",
        "proof_of_service",
        "order",
        "letters",
        "closing",
    ]
    assert "determination of heirs" in intestate[0]["title"]
    assert "30.1-12-08" in testate[4]["statute"]
    assert forms.formal_checklist("informal_testate") == ()


def test_companion_forms_are_in_the_manifest_and_renderable():
    for slug, _kind, _description in forms.PACK_SAMPLES[1:]:
        entry = _manifest_entry(slug)
        content = (SEED_DIR / entry["filename"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
        assert len(discover_pdf_fields(content)) == entry["field_count"]
