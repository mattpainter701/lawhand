"""The committed firm-paperwork samples must match the module that authors them.

``backend/scripts/build_library_intake_forms.py`` is the source of the fee
agreement, the prospective-client intake form, and the client questionnaire in
the global library; the PDFs in ``backend/seed/sample_templates`` are its
artifacts. If the two drift, a firm fills a form whose fields no longer map to
the variables the platform reads back.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.services.pdf_templates import discover_pdf_fields
from app.services.template_bindings import is_valid_binding

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "scripts" / "build_library_intake_forms.py"
SEED_DIR = BACKEND / "seed" / "sample_templates"
#: The template studio refuses a PDF with more widgets than this.
WIDGET_LIMIT = 200


@pytest.fixture(scope="module")
def builder():
    spec = importlib.util.spec_from_file_location("library_intake_forms", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # The script defines dataclasses, whose field resolution looks the defining
    # module up in sys.modules; a module loaded by path alone is not there yet.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manifest():
    forms = json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))[
        "forms"
    ]
    return {form["slug"]: form for form in forms}


def _forms(builder):
    return list(builder.FORMS)


def test_every_authored_form_is_in_the_manifest(builder, manifest):
    for form in _forms(builder):
        entry = manifest[form.slug]
        assert entry["origin"] == "authored"
        assert entry["filename"] == form.filename
        assert entry["title"] == form.title
        assert entry["category"] == form.category


def test_committed_pdf_carries_the_fields_the_module_declares(builder, manifest):
    """A field the module dropped or renamed is a variable the form can no
    longer collect, whatever the committed PDF still shows."""

    for form in _forms(builder):
        committed = (SEED_DIR / form.filename).read_bytes()
        rendered = builder.render(form)
        assert {field["name"] for field in discover_pdf_fields(committed)} == {
            field["name"] for field in discover_pdf_fields(rendered)
        }, f"{form.slug} is out of date: rerun build_library_intake_forms.py"
        assert manifest[form.slug]["field_count"] == len(discover_pdf_fields(committed))


def test_every_field_is_labelled_and_uniquely_named(builder):
    for form in _forms(builder):
        names = [entry.name for entry in form.fields()]
        for entry in form.fields():
            assert entry.label.strip(), f"{form.slug}: {entry.name} has no label"
        # A name may repeat — the client's name over the signature line is the
        # same value as in the opening block, and viewers keep the two in sync —
        # but a repeat must carry the same meaning, never two different fields.
        repeated = {name for name in names if names.count(name) > 1}
        for name in repeated:
            bindings = {entry.binding for entry in form.fields() if entry.name == name}
            assert len(bindings) == 1, f"{form.slug}: {name} declares two bindings"


def test_forms_stay_under_the_studio_widget_limit(builder):
    for form in _forms(builder):
        widgets = len(form.fields())
        assert (
            widgets <= WIDGET_LIMIT
        ), f"{form.slug} has {widgets} widgets, over the studio's limit"


def test_declared_bindings_exist_in_the_catalogue(builder, manifest):
    for form in _forms(builder):
        declared = form.bindings()
        assert declared, f"{form.slug} declares no bindings"
        assert manifest[form.slug]["bindings"] == dict(sorted(declared.items()))
        for name, path in declared.items():
            assert is_valid_binding(path), f"{form.slug}: {name} -> {path}"


def test_the_fee_agreement_serves_every_matter_type(builder):
    """One agreement covers the firm: the arrangement is chosen on the form."""

    agreement = builder.FEE_AGREEMENT
    names = {entry.name for entry in agreement.fields()}
    assert {
        "fee_basis_hourly",
        "fee_basis_flat",
        "fee_basis_contingency",
        "fee_basis_hybrid",
        "fee_basis_recurring",
    } <= names
    assert {
        "practice_area_family",
        "practice_area_criminal",
        "practice_area_injury",
        "practice_area_estate",
        "practice_area_business",
        "practice_area_real_estate",
        "practice_area_immigration",
        "practice_area_employment",
        "practice_area_litigation",
        "practice_area_bankruptcy",
    } <= names
    # Regulated wording stays the firm's to write rather than being guessed at.
    assert {
        "trust_account_terms",
        "dispute_resolution_terms",
        "jurisdiction_required_terms",
    } <= names


def test_no_default_suggests_an_amount_a_firm_must_decide(builder):
    """A printed number would read as advice about what a firm should charge.

    A default belongs only on a term a convention settles — a billing
    increment, a notice period — never on a rate, a retainer, or a fee.
    """

    settled = {
        "billing_increment",
        "minimum_time_charge",
        "payment_due_days",
        "recurring_fee_notice",
    }
    for form in _forms(builder):
        for entry in form.fields():
            if not entry.default:
                continue
            assert (
                entry.name in settled
            ), f"{form.slug}: {entry.name} must not carry a suggested value"
            assert (
                "$" not in entry.default and "%" not in entry.default
            ), f"{form.slug}: {entry.name} suggests an amount"
