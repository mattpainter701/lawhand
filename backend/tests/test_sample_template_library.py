"""Global sample-template library: catalog integrity and read-only isolation.

These tests run without a live database. They prove the committed catalog is
coherent (every manifest entry maps to a real, renderable PDF whose SHA-256 and
field count match) and that the catalog is platform-owned read-only content —
no ``tenant_id`` column and no tenant mutation endpoints.
"""

import hashlib
import io
import json
import re
import uuid
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


def test_imported_undefined_labels_get_honest_review_labels():
    fields = discover_pdf_fields(
        (SEED_DIR / "advance_directive" / "nevada-living-will.pdf").read_bytes()
    )
    assert fields
    assert not any(
        field["label"].strip().casefold().startswith("undefined") for field in fields
    )
    fallback_fields = [field for field in fields if field.get("source_label", "").casefold().startswith("undefined")]
    assert fallback_fields
    assert all(field["label"].startswith("Source field ") for field in fallback_fields)


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


# ── Provenance and duplicate titles (#504) ──────────────────────────────────


_PROVENANCE_FIELDS = {
    "source_name",
    "source_url",
    "edition",
    "retrieved_at",
    "source_files",
}


def test_manifest_provenance_uses_only_documented_fields():
    # Provenance is what tells a user which of several same-titled forms they
    # are about to file, so the schema is pinned rather than free-form. See
    # backend/seed/sample_templates/README.md.
    for form in _manifest()["forms"]:
        provenance = form.get("provenance")
        if provenance is None:
            continue
        assert isinstance(provenance, dict), form["slug"]
        assert set(provenance) <= _PROVENANCE_FIELDS, form["slug"]


def test_the_seeder_rejects_an_unknown_provenance_field():
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "scripts"))
    from seed_sample_templates import _provenance

    assert _provenance({"slug": "x"}) is None
    assert _provenance({"slug": "x", "provenance": {}}) is None
    assert _provenance(
        {"slug": "x", "provenance": {"source_name": "Example Courts"}}
    ) == {"source_name": "Example Courts"}
    with pytest.raises(SystemExit):
        _provenance({"slug": "x", "provenance": {"guessed_edition": "2024"}})
    with pytest.raises(SystemExit):
        _provenance({"slug": "x", "provenance": "Example Courts"})


def test_duplicate_titles_are_distinct_files_not_byte_duplicates():
    """#504: the repeated titles cannot be mechanically de-duplicated.

    If this ever fails because two same-titled forms share a digest, the right
    fix is to drop one from the manifest — not to label them apart.
    """

    by_title: dict[str, list[dict]] = {}
    for form in _manifest()["forms"]:
        by_title.setdefault(form["title"].strip().lower(), []).append(form)

    duplicates = {
        title: forms for title, forms in by_title.items() if len(forms) > 1
    }
    assert duplicates, "expected the known duplicate-titled variants"
    for title, forms in duplicates.items():
        digests = {form["sha256"] for form in forms}
        assert len(digests) == len(forms), f"{title} has byte-identical variants"


# ── Curated court forms: bindings and option labels ─────────────────────────


def _seeder():
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "scripts"))
    import seed_sample_templates

    return seed_sample_templates


def _seeded_schema(slug: str) -> dict:
    form = next(form for form in _manifest()["forms"] if form["slug"] == slug)
    return _seeder()._variable_schema(
        (SEED_DIR / form["filename"]).read_bytes(),
        form.get("bindings"),
        form.get("option_labels"),
        form.get("field_labels"),
    )


_OHIO_DIVORCE = (
    "ohio-divorce-no-children",
    "ohio-divorce-with-children",
    "ohio-divorce-with-children-2",
)


def test_every_manifest_form_seeds_with_its_curation():
    # The seeder refuses a binding or option label naming something the PDF
    # lacks, so this is the check that no curated entry has drifted.
    for form in _manifest()["forms"]:
        _seeded_schema(form["slug"])


@pytest.mark.parametrize("slug", _OHIO_DIVORCE)
def test_ohio_divorce_caption_and_signature_block_fill_from_the_right_records(slug):
    from app.services import template_fill_engine as engine
    from app.services import template_firm_fields
    from tests.fill_campaign import probe

    fields = _seeded_schema(slug)["fields"]
    bindings = {field["name"]: field["binding"] for field in fields if field.get("binding")}
    records = probe.probe_records()
    records.matter.client.email = "client@example.com"
    records.matter.client.phone = "555-0199"
    candidates = engine.collect(records)
    firm = template_firm_fields.resolve(
        {"firm_phone": "555-0000"}, uuid.uuid4(), bindings
    )
    resolved = {
        item.variable: item
        for item in engine.resolve_variables(
            [field["name"] for field in fields],
            bindings=bindings,
            candidates=candidates,
            firm=firm,
            custom={},
        )
    }
    by_path = {path: name for name, path in bindings.items()}

    assert resolved[by_path["matter.judge"]].suggested_value == "Probe Judge"
    assert resolved[by_path["matter.case_number"]].suggested_value == "PR-0"
    assert resolved[by_path["party.plaintiff.name"]].suggested_value
    assert resolved[by_path["party.defendant.name"]].suggested_value
    assert resolved[by_path["attorney.name"]].suggested_value == "Probe Attorney"
    # The signature block is the filer's: before curation "Email" and
    # "Phone Number" matched the client's details by name.
    assert resolved[by_path["attorney.email"]].suggested_value == "probe@firm.com"
    assert resolved[by_path["firm.phone"]].suggested_value == "555-0000"
    values = {item.suggested_value for item in resolved.values()}
    assert "client@example.com" not in values
    assert "555-0199" not in values
    for name, path in bindings.items():
        if path == "manual":
            assert resolved[name].suggested_value is None
            assert resolved[name].provenance["status"] == "manual_entry"


def test_radio_options_follow_the_page_and_carry_readable_labels():
    for slug, name in (
        ("ohio-divorce-with-children", "pregnancy"),
        ("ohio-divorce-with-children-2", "neither_party_is_pregnant_or_a_party_is_pregnant"),
    ):
        form = next(form for form in _manifest()["forms"] if form["slug"] == slug)
        discovered = {
            field["name"]: field
            for field in discover_pdf_fields((SEED_DIR / form["filename"]).read_bytes())
        }
        # The PDF's own state list reads "Choice 2" first for the -2 variant;
        # discovery offers the buttons in the order the page shows them.
        assert discovered[name]["options"] == ["Choice 1", "Choice 2"]
        seeded = {field["name"]: field for field in _seeded_schema(slug)["fields"]}
        assert seeded[name]["options"] == [
            {"value": "Choice 1", "label": "Neither party is pregnant"},
            {"value": "Choice 2", "label": "A party is pregnant"},
        ]


def test_labelled_radio_values_still_fill_the_pdf():
    from app.services.pdf_templates import fill_pdf_template

    form = next(
        form
        for form in _manifest()["forms"]
        if form["slug"] == "ohio-divorce-with-children-2"
    )
    content = (SEED_DIR / form["filename"]).read_bytes()
    output = fill_pdf_template(
        content,
        variable_schema=_seeded_schema(form["slug"]),
        variables={"neither_party_is_pregnant_or_a_party_is_pregnant": "Choice 2"},
        flatten=False,
        enforce_required=False,
    )
    fields = PdfReader(io.BytesIO(output)).get_fields()
    assert (
        str(fields["Neither party is pregnant or a party is pregnant"]["/V"])
        == "/Choice 2"
    )


def test_the_seeder_rejects_curation_the_pdf_does_not_support():
    seeder = _seeder()
    content = (
        SEED_DIR / "court_form" / "ohio-divorce-with-children-2.pdf"
    ).read_bytes()
    with pytest.raises(SystemExit, match="unknown field"):
        seeder._variable_schema(content, {"no_such_field": "matter.judge"})
    with pytest.raises(SystemExit, match="Unknown binding path"):
        seeder._variable_schema(content, {"judge_name": "matter.nope"})
    with pytest.raises(SystemExit, match="non-option field"):
        seeder._variable_schema(content, None, {"judge_name": {"A": "B"}})
    with pytest.raises(SystemExit, match="labels unknown field"):
        seeder._variable_schema(content, None, None, {"no_such_field": "Judge"})
    with pytest.raises(SystemExit, match="non-empty text"):
        seeder._variable_schema(content, None, None, {"judge_name": "  "})
    labelled = seeder._variable_schema(content, None, None, {"judge_name": " Judge "})
    judge = next(field for field in labelled["fields"] if field["name"] == "judge_name")
    assert (judge["label"], judge["label_source"]) == ("Judge", "curated")
    assert judge["source_label"] == "Insert name of Judge"
    with pytest.raises(SystemExit, match="unknown option"):
        seeder._variable_schema(
            content,
            None,
            {"neither_party_is_pregnant_or_a_party_is_pregnant": {"Choice 3": "x"}},
        )
    schema = seeder._variable_schema(
        content,
        None,
        {"neither_party_is_pregnant_or_a_party_is_pregnant": {"Choice 1": "Neither"}},
    )
    radio = next(field for field in schema["fields"] if field["field_type"] == "radio")
    # An option left unlabelled keeps its export value as the label.
    assert radio["options"] == [
        {"value": "Choice 1", "label": "Neither"},
        {"value": "Choice 2", "label": "Choice 2"},
    ]


def test_a_rebuild_carries_curation_only_to_unchanged_files(tmp_path):
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts" / "build_sample_template_library.py"
    spec = importlib.util.spec_from_file_location("build_sample_library", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "forms": [
                    {"slug": "a", "sha256": "aa", "bindings": {"x": "matter.judge"},
                     "option_labels": {"r": {"1": "One"}}},
                    {"slug": "b", "sha256": "bb"},
                    {"slug": "c", "sha256": "cc", "origin": "authored",
                     "bindings": {"y": "client.name"}},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert module._curation_by_digest(tmp_path) == {
        "aa": {"bindings": {"x": "matter.judge"}, "option_labels": {"r": {"1": "One"}}}
    }
    assert module._curation_by_digest(tmp_path / "missing") == {}


# ── Catalog-wide curation invariants ────────────────────────────────────────

#: Labels that tell a person nothing about what goes in the box: the PDF's own
#: tool-generated names ("Text3", "Check Box4", "undefined 2"), the discovery
#: fallback ("Source field 12 (page 1)"), bare numbers, and one- or two-letter
#: fragments.
_PLACEHOLDER_LABEL = re.compile(
    r"^(source field \d+.*|undefined[\s_]*\d*|text[\s_]*(field)?[\s_]*\d*"
    r"|check[\s_]*box[\s_]*\d*|field[\s_]*\d+|fill[\s_]*\d+|group[\s_]*\d+"
    r"|radio[\s_]*button[\s_]*\d*|toggle[\s_]*\d*|dropdown[\s_]*\d*"
    r"|button[\s_]*\d*|[\d\s_.,-]+|[a-z]{1,2}[\s_]*\d*)$",
    re.I,
)
_MAX_LABEL = 90


def _curated_forms() -> list[dict]:
    # Authored forms are generated in-repo with field names that already are the
    # platform's variables; everything else arrives with a stranger's PDF names.
    return [form for form in _manifest()["forms"] if form.get("origin") != "authored"]


def test_every_shared_form_labels_each_field_readably_and_uniquely():
    problems = []
    for form in _curated_forms():
        seen: dict[str, list[str]] = {}
        for field in _seeded_schema(form["slug"])["fields"]:
            label = field["label"].strip()
            if _PLACEHOLDER_LABEL.match(label):
                problems.append(f"{form['slug']}: {field['name']} is labelled {label!r}")
            if len(label) > _MAX_LABEL:
                problems.append(f"{form['slug']}: {field['name']} label is too long")
            seen.setdefault(label.casefold(), []).append(field["name"])
        problems.extend(
            f"{form['slug']}: {names} share the label {label!r}"
            for label, names in seen.items()
            if len(names) > 1
        )
    assert problems == [], "\n".join(problems[:40])


def test_no_shared_form_fills_a_field_by_accidental_name_match():
    # A generic PDF name ("Address", "Email", "Full Name") matches a client
    # alias, so an unbound field would fill with the client's details even
    # when the box belongs to a landlord, a witness or the attorney. Every
    # such field must say where its value comes from, or that it is typed.
    from app.services.template_fill_engine import normalize_variable_name, vocabulary

    names = vocabulary()
    unbound = [
        f"{form['slug']}: {field['name']}"
        for form in _curated_forms()
        for field in _seeded_schema(form["slug"])["fields"]
        if normalize_variable_name(field["name"]) in names and not field.get("binding")
    ]
    assert unbound == []


def test_every_shared_option_reads_as_what_the_page_prints():
    unreadable = []
    for form in _curated_forms():
        for field in _seeded_schema(form["slug"])["fields"]:
            for option in field["options"]:
                label = str(option["label"] if isinstance(option, dict) else option)
                if label.strip().lower() in {"yes", "no"}:
                    continue
                if _PLACEHOLDER_LABEL.match(label) or re.fullmatch(
                    r"choice\s*\d+", label, re.I
                ):
                    unreadable.append(f"{form['slug']}: {field['name']} -> {label!r}")
    assert unreadable == []


def test_a_builder_rewrite_keeps_curation_for_the_same_bytes(tmp_path):
    from scripts.build_library_intake_forms import update_manifest

    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "forms": [
                    {"slug": "same", "sha256": "aa", "category": "c", "title": "A",
                     "bindings": {"x": "matter.judge"},
                     "field_labels": {"x": "Judge"}},
                    {"slug": "moved", "sha256": "bb", "category": "c", "title": "B",
                     "field_labels": {"y": "Old"}},
                    {"slug": "owned", "sha256": "cc", "category": "c", "title": "C",
                     "bindings": {"z": "client.name"}},
                ]
            }
        ),
        encoding="utf-8",
    )
    update_manifest(
        [
            {"slug": "same", "sha256": "aa", "category": "c", "title": "A", "bindings": {}},
            {"slug": "moved", "sha256": "b2", "category": "c", "title": "B"},
            {"slug": "owned", "sha256": "cc", "category": "c", "title": "C",
             "bindings": {"z": "client.email"}},
        ],
        tmp_path,
    )
    by_slug = {
        form["slug"]: form
        for form in json.loads((tmp_path / "manifest.json").read_text())["forms"]
    }
    assert by_slug["same"]["bindings"] == {"x": "matter.judge"}
    assert by_slug["same"]["field_labels"] == {"x": "Judge"}
    # New bytes may have new field names, so their curation does not carry.
    assert "field_labels" not in by_slug["moved"]
    # A builder that declares bindings owns them.
    assert by_slug["owned"]["bindings"] == {"z": "client.email"}
