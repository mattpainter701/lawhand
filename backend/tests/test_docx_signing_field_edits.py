"""Saving a Word signing field's role, kind and anchor through the field map.

A Word field's edit may only add keys the map allows; a signing field's role,
its signature-or-initials kind and the caption it anchors to are among them,
because Template Studio saves exactly those. An anchor that is present must
name a caption -- an empty one would bind to nothing at generation.
"""

import io

import pytest
from docx import Document

from app.services.docx_outline import validate_visual_field_map
from app.services.docx_templates import TemplateDocxError


def _docx(*paragraphs) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


SOURCE = _docx("Client Signature: ____")
BLANK = {
    "name": "client_signature",
    "label": "Client signature",
    "field_type": "text",
    "required": False,
    "source_text": "____",
    "docx_anchor": {"paragraph_ordinal": 0, "start": 18, "end": 22},
}
CURRENT = {"fields": [BLANK]}


def proposed(**changes):
    return {"fields": [{**BLANK, **changes}]}


def test_a_blank_can_become_a_signing_field_with_a_role_and_kind():
    validate_visual_field_map(
        SOURCE,
        CURRENT,
        proposed(field_type="signature", signer_role="client", signing_type="initials"),
    )


def test_a_signing_field_can_name_the_caption_it_sits_beside():
    validate_visual_field_map(
        SOURCE,
        CURRENT,
        proposed(
            field_type="signature",
            signer_role="client",
            pdf_anchor={"text": "Client Signature:", "placement": "after"},
        ),
    )


def test_an_anchor_without_a_placement_is_fine():
    validate_visual_field_map(
        SOURCE, CURRENT, proposed(field_type="signature", pdf_anchor={"text": "By:"})
    )


@pytest.mark.parametrize(
    "anchor,message",
    [
        ({"text": ""}, "must name the caption"),
        ({"text": "   "}, "must name the caption"),
        ("Client Signature:", "must name the caption"),
        ({"placement": "after"}, "must name the caption"),
        ({"text": "x" * 201}, "too long"),
        ({"text": "By:", "placement": "sideways"}, "after, before, or below"),
        ({"text": "By:", "rect": [1, 2, 3, 4]}, "unexpected keys"),
    ],
)
def test_a_present_anchor_must_be_a_usable_one(anchor, message):
    with pytest.raises(TemplateDocxError, match=message):
        validate_visual_field_map(
            SOURCE, CURRENT, proposed(field_type="signature", pdf_anchor=anchor)
        )


def test_a_field_that_never_mentions_an_anchor_is_not_asked_for_one():
    validate_visual_field_map(SOURCE, CURRENT, proposed(field_type="signature"))


def test_other_unknown_keys_are_still_refused():
    with pytest.raises(TemplateDocxError, match="text selection"):
        validate_visual_field_map(SOURCE, CURRENT, proposed(pdf_overlay={"page": 1}))
