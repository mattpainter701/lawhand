"""Human review of a PDF scan, and the publish gate that now enforces it.

Before this, the attestation the wizard asked for ("I compared every
highlighted field with the original document") disabled a button in the browser
and was never sent anywhere. Nothing stored it and nothing re-checked it, so a
template of OCR guesses could be published and used to generate real documents.
Word templates already had the enforced version of this; these tests cover the
same property for the other half of the product.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.document_templates import (
    _ensure_pdf_source_review,
    _stamp_pdf_source_review,
)
from app.services import pdf_source_review


def _schema(fields, **extra):
    return {"fields": list(fields), **extra}


def _confirm(schema):
    schema["pdf_source_review"] = {"confirmed": True}
    _stamp_pdf_source_review(schema)
    return schema


class TestWhatNeedsReviewing:
    def test_a_field_the_scan_scored_low_needs_a_person(self):
        assert pdf_source_review.field_needs_review({"confidence": 0.4})
        assert not pdf_source_review.field_needs_review({"confidence": 0.99})

    def test_a_field_read_off_pixels_needs_a_person(self):
        assert pdf_source_review.field_needs_review(
            {"confidence": 1, "pdf_overlays": [{"source_kind": "ocr"}]}
        )
        assert not pdf_source_review.field_needs_review(
            {"confidence": 1, "pdf_overlays": [{"source_kind": "acroform"}]}
        )

    def test_an_unreadable_confidence_is_not_a_confident_one(self):
        assert pdf_source_review.field_needs_review({"confidence": "high"})

    def test_an_ocr_scan_is_uncertain_as_a_whole(self):
        # Not only where it happened to score a field low: the method says the
        # page was read as an image, so every box on it is a guess.
        schema = _schema(
            [{"name": "a", "confidence": 1.0}], detection={"method": "ocr_fallback"}
        )
        assert pdf_source_review.requires_review(schema)

    def test_an_excluded_field_is_nobody_s_to_check(self):
        schema = _schema([{"name": "a", "confidence": 0.1, "included": False}])
        assert not pdf_source_review.requires_review(schema)

    def test_a_clean_scan_asks_for_no_ceremony(self):
        # The gate is for fields the scan is unsure of, not a step on every
        # template.
        schema = _schema([{"name": "a", "confidence": 1.0}])
        assert not pdf_source_review.requires_review(schema)
        assert pdf_source_review.unresolved_reason(schema) is None


class TestTheAttestation:
    def test_the_server_decides_what_a_confirmation_covers(self):
        # A client supplying its own digest could attest to a field set other
        # than the one it is saving, which is the one thing this prevents.
        schema = _schema([{"name": "a", "confidence": 0.4}])
        schema["pdf_source_review"] = {"confirmed": True, "confirmed_digest": "forged"}
        _stamp_pdf_source_review(schema)
        assert schema["pdf_source_review"]["confirmed_digest"] != "forged"
        assert pdf_source_review.review_is_current(schema)

    def test_an_unconfirmed_save_clears_a_previous_attestation(self):
        # It would re-arm at publish anyway, but leaving it on the row would
        # show a reviewed template that publish then refuses.
        schema = _confirm(_schema([{"name": "a", "confidence": 0.4}]))
        _stamp_pdf_source_review(schema)
        assert "pdf_source_review" not in schema

    def test_confirming_survives_an_edit_that_moves_no_box(self):
        # A label or a binding is not what a person checked against the source.
        schema = _confirm(_schema([{"name": "a", "confidence": 0.4, "label": "A"}]))
        schema["fields"][0]["label"] = "Renamed"
        schema["fields"][0]["binding"] = "client.name"
        assert pdf_source_review.review_is_current(schema)

    @pytest.mark.parametrize(
        "change",
        [
            pytest.param({"page": 3}, id="moved to another page"),
            pytest.param({"confidence": 0.2}, id="rescanned less confidently"),
            pytest.param({"review_required": True}, id="flagged by a rescan"),
            pytest.param(
                {"pdf_overlays": [{"page": 1, "rect": [1, 2, 3, 4]}]}, id="box moved"
            ),
        ],
    )
    def test_confirming_does_not_survive_a_change_to_the_page(self, change):
        schema = _confirm(_schema([{"name": "a", "confidence": 0.4}]))
        schema["fields"][0].update(change)
        assert not pdf_source_review.review_is_current(schema)

    def test_a_new_field_re_arms_the_review(self):
        schema = _confirm(_schema([{"name": "a", "confidence": 0.4}]))
        schema["fields"].append({"name": "b", "confidence": 1.0})
        assert not pdf_source_review.review_is_current(schema)

    def test_reordering_the_same_fields_does_not_re_arm_it(self):
        first = {"name": "a", "confidence": 0.4}
        second = {"name": "b", "confidence": 1.0}
        schema = _confirm(_schema([first, second]))
        schema["fields"] = [second, first]
        assert pdf_source_review.review_is_current(schema)


class TestThePublishGate:
    def _publish(self, schema, template_format="pdf"):
        _ensure_pdf_source_review(SimpleNamespace(format=template_format), schema)

    def test_an_unreviewed_scan_cannot_be_published(self):
        with pytest.raises(HTTPException) as refusal:
            self._publish(_schema([{"name": "a", "confidence": 0.4}]))
        assert refusal.value.status_code == 422
        assert "not sure of" in refusal.value.detail

    def test_a_reviewed_scan_can_be_published(self):
        self._publish(_confirm(_schema([{"name": "a", "confidence": 0.4}])))

    def test_a_review_that_no_longer_describes_the_page_says_so(self):
        # The two states need different sentences: never confirmed, versus
        # confirmed against fields that have since changed.
        schema = _confirm(_schema([{"name": "a", "confidence": 0.4}]))
        schema["fields"].append({"name": "b", "confidence": 0.3})
        with pytest.raises(HTTPException) as refusal:
            self._publish(schema)
        assert "changed after" in refusal.value.detail

    def test_a_word_template_is_not_gated_here(self):
        # Word has its own source review, recomputed from the live document.
        self._publish(_schema([{"name": "a", "confidence": 0.4}]), "docx")

    def test_a_markdown_template_has_no_scan_to_review(self):
        self._publish(_schema([{"name": "a", "confidence": 0.4}]), "markdown")
