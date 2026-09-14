"""Global sample-template library: catalog integrity and read-only isolation.

These tests run without a live database. They prove the committed catalog is
coherent (every manifest entry maps to a real, renderable PDF whose SHA-256 and
field count match) and that the catalog is platform-owned read-only content —
no ``tenant_id`` column and no tenant mutation endpoints.
"""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from pypdf import PdfReader

from app.models.sample_template import SampleTemplate
from app.routers import sample_templates
from app.services.pdf_templates import TemplatePdfError, discover_pdf_fields

SEED_DIR = Path(__file__).resolve().parents[1] / "seed" / "sample_templates"

# Third-party source/copyright branding that must never ship in the catalog.
_SOURCE_MARKERS = (
    "ilovepdf", "freeforms", "made fillable by", "freeprintablelegalforms",
    "justia", "downloaded from", "honoring choices", "honoringchoices",
    "vhha.com", "aoausa.com", "caanet.org", "rocketlawyer", "legalzoom",
    "lawdepot", "formswift", "uslegalforms", "findlegalforms",
    "templateroller", "this form is provided by", "provided courtesy of",
    "esign.com", "www.esign",
)


def _manifest() -> dict:
    return json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_is_populated_with_unique_slugs():
    forms = _manifest()["forms"]
    assert forms, "the sample-template manifest must not be empty"
    slugs = [form["slug"] for form in forms]
    assert len(slugs) == len(set(slugs)), "sample slugs must be unique"


def test_every_sample_source_matches_manifest_and_is_renderable():
    forms = _manifest()["forms"]
    for form in forms:
        source = SEED_DIR / form["filename"]
        assert source.is_file(), f"missing source for {form['slug']}"
        content = source.read_bytes()
        assert (
            hashlib.sha256(content).hexdigest() == form["sha256"]
        ), f"sha256 mismatch for {form['slug']}"
        try:
            fields = discover_pdf_fields(content)
        except TemplatePdfError as exc:
            raise AssertionError(
                f"{form['slug']} is not renderable by the studio: {exc}"
            ) from exc
        assert fields, f"{form['slug']} has no discovered fields"
        assert len(fields) == form["field_count"], (
            f"{form['slug']} field count drifted: "
            f"manifest={form['field_count']} actual={len(fields)}"
        )


def test_catalog_is_platform_owned_and_not_tenant_scoped():
    # Shared content must not carry a tenant_id; tenants read the same rows.
    column_names = [column.name for column in SampleTemplate.__table__.columns]
    assert "tenant_id" not in column_names


def test_catalog_has_no_source_branding_or_metadata():
    # Source identity must never leak: no authoring metadata and no visible
    # third-party source/copyright watermark in any committed sample.
    for form in _manifest()["forms"]:
        source = SEED_DIR / form["filename"]
        reader = PdfReader(source, strict=False)
        if reader.is_encrypted:
            reader.decrypt("")
        assert not reader.metadata, f"{form['slug']} still carries PDF metadata"
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        lowered = text.lower()
        for marker in _SOURCE_MARKERS:
            assert marker not in lowered, (
                f"{form['slug']} contains source marker {marker!r}"
            )


def test_catalog_router_exposes_no_tenant_mutation_endpoints():
    mutating = {"PUT", "PATCH", "DELETE"}
    for route in sample_templates.router.routes:
        methods = {method for method in (getattr(route, "methods", None) or set())}
        assert not (methods & mutating), (
            f"sample catalog must be read-only, got {methods} on {route.path}"
        )


def test_safe_generated_filename_sanitizes():
    assert sample_templates._safe_generated_filename("A/B:C", "pdf") == "A_B_C.pdf"
    assert sample_templates._safe_generated_filename("..", "pdf") == "sample.pdf"


def test_verified_source_rejects_sha256_mismatch(tmp_path, monkeypatch):
    payload = b"%PDF-1.4 fake"
    (tmp_path / "sample.pdf").write_bytes(payload)
    monkeypatch.setattr(sample_templates.settings, "SAMPLE_TEMPLATE_DIR", str(tmp_path))

    class _Sample:
        source_filename = "sample.pdf"
        source_sha256 = hashlib.sha256(b"other").hexdigest()

    with pytest.raises(HTTPException) as exc_info:
        sample_templates._verified_source(_Sample())
    assert exc_info.value.status_code == 409


# The firm-paperwork samples are authored in
# backend/scripts/build_library_intake_forms.py rather than scraped, and their
# whole point is that every field is named after a variable the platform
# already fills from. These tests hold that contract.
AUTHORED_SLUGS = {
    "general-legal-services-fee-agreement",
    "prospective-client-intake-form",
    "client-questionnaire",
}


def _authored() -> list[dict]:
    return [
        form for form in _manifest()["forms"] if form.get("origin") == "authored"
    ]


def test_authored_firm_paperwork_is_in_the_catalog():
    slugs = {form["slug"] for form in _authored()}
    assert AUTHORED_SLUGS <= slugs
    by_slug = {form["slug"]: form for form in _authored()}
    assert by_slug["general-legal-services-fee-agreement"]["category"] == (
        "engagement_letter"
    )
    assert by_slug["prospective-client-intake-form"]["category"] == "intake"
    assert by_slug["client-questionnaire"]["category"] == "intake"


def test_authored_bindings_are_valid_and_name_real_fields():
    from app.services.template_bindings import is_valid_binding

    for form in _authored():
        bindings = form.get("bindings") or {}
        assert bindings, f"{form['slug']} declares no bindings"
        content = (SEED_DIR / form["filename"]).read_bytes()
        names = {field["name"] for field in discover_pdf_fields(content)}
        for name, path in bindings.items():
            assert name in names, f"{form['slug']} binds unknown field {name!r}"
            assert is_valid_binding(path), (
                f"{form['slug']} field {name!r} declares unknown binding {path!r}"
            )


def test_authored_forms_carry_the_client_and_matter_variables():
    # A returned form is only worth collecting if its answers land on the
    # bindings the rest of the document automation fills from.
    required = {
        "general-legal-services-fee-agreement": {
            "client_name": "client.name",
            "matter_name": "matter.name",
            "hourly_rate": "matter.hourly_rate",
            "contingency_percentage": "matter.contingency_percentage",
            "retainer_amount": "matter.retainer_amount",
            "venue": "matter.venue",
        },
        "prospective-client-intake-form": {
            "client_name": "client.name",
            "client_email": "client.email",
            "matter_description": "matter.description",
            "counterparty": "matter.counterparty",
            "case_number": "matter.case_number",
        },
        "client-questionnaire": {
            "client_name": "client.name",
            "counterparty": "matter.counterparty",
            "court": "matter.court",
            "judge": "matter.judge",
        },
    }
    by_slug = {form["slug"]: form for form in _authored()}
    for slug, expected in required.items():
        bindings = by_slug[slug].get("bindings") or {}
        for name, path in expected.items():
            assert bindings.get(name) == path, (
                f"{slug} should bind {name!r} to {path!r}"
            )


def test_authored_samples_render_through_the_product_filler():
    # The catalog's own render endpoint fills and flattens with this function;
    # a sample that cannot survive it is not usable however good it looks.
    from app.services.pdf_templates import fill_pdf_template

    for form in _authored():
        content = (SEED_DIR / form["filename"]).read_bytes()
        fields = discover_pdf_fields(content)
        schema = {"version": 1, "source": "sample_library", "fields": fields}
        values = {
            field["name"]: ("true" if field["field_type"] == "checkbox" else "Sample")
            for field in fields[:8]
        }
        output = fill_pdf_template(
            content,
            variable_schema=schema,
            variables=values,
            flatten=True,
            enforce_required=False,
        )
        assert output.startswith(b"%PDF-")


def test_fee_agreement_covers_every_common_fee_arrangement():
    # One agreement has to serve the whole firm, so each arrangement is a
    # checkbox on the same form rather than a separate template per practice.
    form = next(
        form
        for form in _authored()
        if form["slug"] == "general-legal-services-fee-agreement"
    )
    content = (SEED_DIR / form["filename"]).read_bytes()
    fields = {field["name"]: field for field in discover_pdf_fields(content)}
    for name in (
        "fee_basis_hourly",
        "fee_basis_flat",
        "fee_basis_contingency",
        "fee_basis_hybrid",
        "fee_basis_recurring",
    ):
        assert fields[name]["field_type"] == "checkbox"
    assert fields["scope_of_representation"]["multiline"]


def test_authored_questionnaire_uses_the_shared_intake_question_keys():
    # The questionnaire's answers have to land on the same keys the platform's
    # own intake questions use, or a returned form cannot be read back.
    from app.services.intake_starter_pack import CORE_QUESTIONS

    form = next(form for form in _authored() if form["slug"] == "client-questionnaire")
    content = (SEED_DIR / form["filename"]).read_bytes()
    names = {field["name"] for field in discover_pdf_fields(content)}
    shared = {question.key for question in CORE_QUESTIONS} & names
    assert shared >= {
        "matter_summary",
        "desired_outcome",
        "other_parties",
        "key_dates",
        "related_proceedings",
        "contact_preferences",
    }
