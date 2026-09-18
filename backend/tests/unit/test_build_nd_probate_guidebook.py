"""The guidebook build step: strips what the studio refuses, keeps the forms."""

import io

from pypdf import PdfReader
from pypdf.generic import DictionaryObject, NameObject, TextStringObject
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.services.pdf_templates import discover_pdf_fields
from app.services.probate import forms
from scripts.build_nd_probate_guidebook import clean


def _packet() -> bytes:
    """Three pages: an instructions page, then two form pages with fields."""

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Synthetic packet")
    pdf.drawString(
        72, 720, "(Rev Sep 2026) Page 1 of 1 of NDPC Forms 2,3,4 Instructions"
    )
    pdf.linkURL("https://example.gov", (72, 700, 200, 715))
    pdf.showPage()
    pdf.drawString(72, 720, "ND Probate Code Form 2")
    pdf.acroForm.textfield(
        name="Court of F2", x=72, y=600, width=200, height=14, fieldFlags="required"
    )
    pdf.acroForm.textfield(name="heirs app", x=72, y=560, width=300, height=14)
    pdf.showPage()
    pdf.drawString(72, 720, "Page 1 of 1 - NDPC Form 4/Rev Sep 2026")
    pdf.acroForm.textfield(name="County Name F4", x=72, y=600, width=200, height=14)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_clean_removes_links_metadata_and_required_bits_and_sets_multiline():
    raw = _packet()
    reader = PdfReader(io.BytesIO(raw), strict=False)
    assert reader.metadata is not None
    assert any(
        annot.get_object().get("/Subtype") == "/Link"
        for annot in (reader.pages[0].get("/Annots") or [])
    )

    cleaned = clean(raw, multiline=("heirs_app",))
    reader = PdfReader(io.BytesIO(cleaned), strict=False)
    assert not reader.metadata
    assert not any(
        annot.get_object().get("/Subtype") == "/Link"
        for page in reader.pages
        for annot in (page.get("/Annots") or [])
    )
    fields = {field["name"]: field for field in discover_pdf_fields(cleaned)}
    assert set(fields) == {"court_of_f2", "heirs_app", "county_name_f4"}
    assert not fields["court_of_f2"]["required"]
    assert fields["heirs_app"]["multiline"]
    assert not fields["court_of_f2"]["multiline"]


def test_page_ranges_skip_instruction_pages_and_read_both_header_styles():
    ranges = forms.page_ranges(clean(_packet()))
    assert ranges == {2: (2, 2), 4: (3, 3)}


def test_clean_drops_the_structure_tree_that_keeps_links_reachable():
    raw = _packet()
    reader = PdfReader(io.BytesIO(raw), strict=False)
    from pypdf import PdfWriter

    writer = PdfWriter(clone_from=reader)
    root = writer._root_object
    tree = DictionaryObject({NameObject("/Type"): NameObject("/StructTreeRoot")})
    root[NameObject("/StructTreeRoot")] = writer._add_object(tree)
    root[NameObject("/Lang")] = TextStringObject("en-US")
    out = io.BytesIO()
    writer.write(out)
    cleaned = clean(out.getvalue())
    reader = PdfReader(io.BytesIO(cleaned), strict=False)
    assert "/StructTreeRoot" not in reader.trailer["/Root"]
    assert reader.trailer["/Root"].get("/Lang") == "en-US"
