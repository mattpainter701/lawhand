"""Template field checks: accidental client fills block a PDF; label issues warn."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import document_templates as routes
from app.services import template_field_quality as quality


def _schema(*fields):
    return {"fields": list(fields)}


class TestAccidentalFills:
    def test_a_generic_name_with_no_binding_would_fill_the_client(self):
        (finding,) = quality.accidental_fills(
            _schema({"name": "email", "label": "Attorney email"})
        )
        assert finding.name == "email"
        assert "'Attorney email' would fill with the client's email" in finding.message
        assert "entered by hand" in finding.message

    def test_the_field_name_is_judged_not_the_label(self):
        (finding,) = quality.accidental_fills(_schema({"name": "Phone_Number"}))
        assert "client's phone" in finding.message
        assert "'Phone Number'" in finding.message

    @pytest.mark.parametrize(
        "field",
        [
            {"name": "email", "binding": "attorney.email"},
            {"name": "address", "binding": "manual"},
            {"name": "name", "value_from": "client_name"},
            # Named after the platform variable: the author meant it.
            {"name": "client_email"},
            {"name": "case_number"},
            {"name": "full_name", "field_type": "signature"},
            {"name": "name", "signer_role": "client"},
            {"name": "city", "included": False},
            {"name": "landlord_name"},
        ],
    )
    def test_declared_deliberate_or_irrelevant_fields_pass(self, field):
        assert quality.accidental_fills(_schema(field)) == []

    @pytest.mark.parametrize("schema", [None, {}, {"fields": "x"}, {"fields": [1, {}]}])
    def test_a_malformed_schema_reports_nothing(self, schema):
        assert quality.accidental_fills(schema) == []
        assert quality.warnings(schema) == []


class TestWarnings:
    def test_tool_generated_labels_are_reported(self):
        names = [
            item.name
            for item in quality.warnings(
                _schema(
                    {"name": "text3", "label": "Text3"},
                    {"name": "check_box4", "label": "Check Box4"},
                    {"name": "undefined_2"},
                    {"name": "a", "label": "Source field 12 (page 1)"},
                    {"name": "b", "label": "20"},
                    {"name": "landlord", "label": "Landlord name"},
                )
            )
        ]
        assert names == ["text3", "check_box4", "undefined_2", "a", "b"]

    def test_long_and_duplicate_labels_are_reported(self):
        findings = quality.warnings(
            _schema(
                {"name": "a", "label": "x" * 91},
                {"name": "b", "label": "Full Name"},
                {"name": "c", "label": "full name"},
            )
        )
        messages = {item.name: item.message for item in findings}
        assert "longer than 90 characters" in messages["a"]
        assert messages["b"] == messages["c"]
        assert "2 fields are labelled 'Full Name'" in messages["b"]

    def test_options_must_say_what_they_choose(self):
        findings = quality.warnings(
            _schema(
                {
                    "name": "pregnancy",
                    "label": "Pregnancy",
                    "options": ["Choice 1", {"value": "Choice 2", "label": "A party is pregnant"}],
                },
                {"name": "served", "label": "Served?", "options": ["Yes", "No"]},
            )
        )
        assert [item.message for item in findings] == [
            "Option 'Choice 1' of 'Pregnancy' does not say what it chooses."
        ]

    def test_summary_carries_both_lists(self):
        assert quality.summary(_schema({"name": "email"}, {"name": "text1"})) == {
            "accidental_fills": [
                {
                    "name": "email",
                    "message": quality.accidental_fills(_schema({"name": "email"}))[0].message,
                }
            ],
            "warnings": [
                {"name": "text1", "message": "'text1' does not say what goes in this field."}
            ],
        }


class TestPublishGate:
    def test_a_pdf_with_an_accidental_fill_cannot_publish(self):
        schema = _schema(*({"name": f"email_{n}"} for n in range(1)), *(
            {"name": name} for name in ("address", "city", "state", "zip", "phone", "name")
        ))
        with pytest.raises(HTTPException) as caught:
            routes._ensure_no_accidental_fills(SimpleNamespace(format="PDF"), schema)
        assert caught.value.status_code == 422
        assert "'address' would fill with the client's street" in caught.value.detail
        assert "(1 more fields like this)" in caught.value.detail

    @pytest.mark.parametrize("fmt", ["pdf", "image"])
    def test_a_bound_pdf_publishes(self, fmt):
        routes._ensure_no_accidental_fills(
            SimpleNamespace(format=fmt), _schema({"name": "email", "binding": "manual"})
        )

    def test_a_word_template_is_not_gated(self):
        routes._ensure_no_accidental_fills(
            SimpleNamespace(format="docx"), _schema({"name": "email"})
        )

    def test_the_template_response_reports_the_checks(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        template = SimpleNamespace(
            id="t1", title="T", body="", category="c", description=None,
            visibility="tenant", layer=None, status="draft", format="pdf",
            module=None, stage=None, jurisdiction=None, kind=None,
            variable_schema=_schema({"name": "email"}, {"name": "text1"}),
            signer_roles=None, branding_profile=None, source_filename="a.pdf",
            source_content_type="application/pdf", source_sha256="0" * 64,
            source_file_size=1, source_storage_path="x", source_evidence_sha256=None,
            source_provenance=None, last_test_rendered_at=None, approved_at=None,
            approved_by_user_id=None, is_active=False, current_version_no=1,
            tested_version_no=None, published_version_no=None,
            created_at=now, updated_at=now,
        )
        response = routes._template_response(template)
        assert [item["name"] for item in response.field_quality["accidental_fills"]] == ["email"]
        assert [item["name"] for item in response.field_quality["warnings"]] == ["text1"]
