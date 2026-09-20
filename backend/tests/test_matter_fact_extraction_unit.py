"""Deterministic extraction unit tests that need no database.

The service's proposition engine is pure: labels in, candidates out. These
tests pin the conservative rules — exact labels, one unambiguous pattern match,
and no value for a target the source never mentions.
"""

from types import SimpleNamespace
import uuid

import pytest

from app.services import intake_extraction_ai, matter_fact_extraction as extraction


def standard_target(binding, *, label=None, max_length=None):
    return extraction.FactTarget(
        key=binding,
        label=label or binding,
        binding=binding,
        kind="standard",
        entity="contact" if binding.startswith("client.") else "matter",
        field=binding.split(".", 1)[1],
        field_type="text",
        options=(),
        max_length=max_length,
        match_keys=extraction._standard_match_keys(binding),
    )


def custom_target(*, key, label, field_key, field_type="text", options=()):
    return extraction.FactTarget(
        key=key,
        label=label,
        binding=key,
        kind="custom_matter",
        entity="matter",
        field="11111111-1111-1111-1111-111111111111",
        field_type=field_type,
        options=tuple(options),
        max_length=None,
        match_keys=frozenset(
            {extraction.normalize_text(label), extraction.normalize_text(field_key)}
        ),
    )


def test_acroform_values_match_by_human_label_and_pdf_name():
    targets = [
        standard_target("client.name"),
        standard_target("matter.court"),
        standard_target("matter.case_number"),
    ]
    found = extraction.extract_candidates(
        text="",
        form_values=[
            {
                "label": "Client Name",
                "pdf_field_name": "Client Name",
                "value": "Jane Q Client",
            },
            {"label": "court", "pdf_field_name": "court", "value": "Superior Court"},
        ],
        targets=targets,
    )
    values = {
        key: [candidate.value for candidate in candidates]
        for key, candidates in found.items()
    }
    assert values["client.name"] == ["Jane Q Client"]
    assert values["matter.court"] == ["Superior Court"]
    # A field the form does not carry yields nothing, not a blank.
    assert "matter.case_number" not in values


def test_label_lines_use_exact_label_and_case_synonyms():
    targets = [standard_target("matter.case_number"), standard_target("client.name")]
    found = extraction.extract_candidates(
        text="Case No.: 2024-CV-001\nClient: John Smith\n\nCase No. was assigned later.\n",
        form_values=[],
        targets=targets,
    )
    assert [c.source_locator for c in found["matter.case_number"]] == ["line:1"]
    assert [c.value for c in found["client.name"]] == ["John Smith"]


def test_pattern_values_require_exactly_one_match():
    targets = [standard_target("client.email"), standard_target("client.address.zip")]
    one = extraction.extract_candidates(
        text="Reach me at jane@example.com anytime.\n",
        form_values=[],
        targets=targets,
    )
    assert [c.value for c in one["client.email"]] == ["jane@example.com"]
    assert [c.source_kind for c in one["client.email"]] == ["regex"]

    ambiguous = extraction.extract_candidates(
        text="Email one@example.com or two@example.com.\n",
        form_values=[],
        targets=targets,
    )
    assert "client.email" not in ambiguous


def test_overlong_standard_value_is_never_proposed():
    target = standard_target("client.name", max_length=10)
    found = extraction.extract_candidates(
        text="",
        form_values=[
            {"label": "Client", "pdf_field_name": "client", "value": "x" * 11}
        ],
        targets=[target],
    )
    assert found == {}


def test_custom_boolean_and_label_matching():
    target = custom_target(
        key="custom.matter.11111111-1111-1111-1111-111111111111",
        label="Has children",
        field_key="has_children",
        field_type="boolean",
    )
    found = extraction.extract_candidates(
        text="Has children: yes\n",
        form_values=[],
        targets=[target],
    )
    assert [c.value for c in found[target.key]] == ["True"]


def test_distinct_folds_duplicate_values_and_keeps_highest_confidence():
    target = standard_target("client.name")
    merged = {
        target.key: [
            extraction.Candidate("Jane Client", "label_value", "line:1", 1.0),
            extraction.Candidate("jane client", "regex", "text", 0.6),
            extraction.Candidate("Someone Else", "label_value", "line:4", 1.0),
        ]
    }
    distinct = extraction._distinct(merged[target.key])
    assert sorted(c.value for c in distinct) == ["Jane Client", "Someone Else"]


async def test_build_targets_includes_standard_and_custom(monkeypatch):
    definition = SimpleNamespace(
        id="22222222-2222-2222-2222-222222222222",
        entity_type="matter",
        field_key="opposing_counsel",
        label="Opposing counsel",
        field_type="text",
        options_json=[],
    )

    async def fake_definitions(_db, _tenant_id):
        return [definition]

    monkeypatch.setattr(
        extraction.template_custom_fields, "definitions", fake_definitions
    )
    targets = await extraction.build_targets(None, "tenant")
    keys = {target.key for target in targets}
    assert "client.name" in keys
    assert "matter.court" in keys
    assert f"custom.matter.{definition.id}" in keys


def test_extraction_flag_defaults_off():
    assert extraction.extraction_enabled(None) is False
    assert extraction.extraction_enabled(SimpleNamespace(custom_config=None)) is False
    assert (
        extraction.extraction_enabled(
            SimpleNamespace(custom_config={"intake_fact_extraction": {"enabled": True}})
        )
        is True
    )


def test_read_pdf_form_values_reads_filled_widgets():
    from io import BytesIO

    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from app.services.pdf_templates import read_pdf_form_values

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter)
    pdf.drawString(72, 720, "Client:")
    pdf.acroForm.textfield(
        name="Client Name", value="Jane Client", x=120, y=705, width=250, height=24
    )
    pdf.acroForm.checkbox(name="approved", checked=True, x=130, y=670, size=15)
    pdf.acroForm.checkbox(name="declined", checked=False, x=200, y=670, size=15)
    pdf.save()
    values = {
        entry["pdf_field_name"]: entry["value"]
        for entry in read_pdf_form_values(output.getvalue())
    }
    assert values["Client Name"] == "Jane Client"
    assert values["approved"] == "true"
    # An unchecked box is omitted: a blank must not masquerade as an answer.
    assert "declined" not in values


def test_reconcile_ai_values_keeps_only_real_then_storable_targets():
    target = standard_target("matter.case_number")
    proposal = intake_extraction_ai.AiExtractionProposal(
        values=[
            {"target_key": "matter.case_number", "value": "2024-CV-001"},
            {"target_key": "invented.target", "value": "whatever"},
        ]
    )
    assert intake_extraction_ai.reconcile_ai_values(proposal, [target]) == {
        "matter.case_number": "2024-CV-001"
    }

    short = standard_target("client.name", max_length=5)
    too_long = intake_extraction_ai.AiExtractionProposal(
        values=[{"target_key": "client.name", "value": "much too long"}]
    )
    assert intake_extraction_ai.reconcile_ai_values(too_long, [short]) == {}


def test_value_in_evidence_grounds_a_reviewed_value_in_the_source():
    assert extraction._value_in_evidence("John Smith", "Client: John Smith", [])
    assert not extraction._value_in_evidence("Nobody", "Client: John Smith", [])
    assert extraction._value_in_evidence(
        "true", "", [{"value": "true", "label": "approved"}]
    )


async def test_extract_with_ai_is_closed_when_the_platform_switch_is_off(monkeypatch):
    monkeypatch.setattr(
        intake_extraction_ai,
        "settings",
        SimpleNamespace(INTAKE_EXTRACTION_ENABLED=False),
    )
    with pytest.raises(intake_extraction_ai.IntakeExtractionUnavailable):
        await intake_extraction_ai.extract_with_ai(
            db=None,
            user=None,
            text="Case No.: 2024-CV-001",
            targets=[standard_target("matter.case_number")],
            document_sha256="a" * 64,
        )


async def test_extract_with_ai_reconciles_and_meters_one_usage_record(monkeypatch):
    monkeypatch.setattr(
        intake_extraction_ai,
        "settings",
        SimpleNamespace(
            INTAKE_EXTRACTION_ENABLED=True,
            INTAKE_EXTRACTION_MODEL="lawhand-intake-extraction",
            INTAKE_EXTRACTION_INPUT_USD_PER_MILLION=0.30,
            INTAKE_EXTRACTION_OUTPUT_USD_PER_MILLION=1.20,
            INTAKE_EXTRACTION_MAX_CHARS=12000,
        ),
    )

    async def fake_budget(_db, _user):
        return None

    monkeypatch.setattr(intake_extraction_ai, "check_token_budget", fake_budget)

    class FakeLLM:
        async def complete(self, **_kwargs):
            return (
                '{"values":[{"target_key":"matter.case_number","value":"2024-CV-001",'
                '"confidence":0.8},{"target_key":"invented","value":"x"}]}',
                100,
                20,
            )

    added: list = []

    class FakeDB:
        def add(self, record):
            added.append(record)

        async def commit(self):
            return None

    values = await intake_extraction_ai.extract_with_ai(
        db=FakeDB(),
        user=SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4(), tenant=None),
        text="Case No.: 2024-CV-001",
        targets=[standard_target("matter.case_number")],
        document_sha256="a" * 64,
        llm=FakeLLM(),
    )
    assert values == {"matter.case_number": "2024-CV-001"}
    assert len(added) == 1
    assert added[0].operation_type == "intake_extraction"
    assert added[0].tokens_in == 100 and added[0].tokens_out == 20
    assert added[0].cost_usd is not None and added[0].cost_usd > 0


async def test_extract_with_ai_reports_provider_and_parse_failures(monkeypatch):
    monkeypatch.setattr(
        intake_extraction_ai,
        "settings",
        SimpleNamespace(
            INTAKE_EXTRACTION_ENABLED=True,
            INTAKE_EXTRACTION_MODEL="lawhand-intake-extraction",
            INTAKE_EXTRACTION_INPUT_USD_PER_MILLION=0.30,
            INTAKE_EXTRACTION_OUTPUT_USD_PER_MILLION=1.20,
            INTAKE_EXTRACTION_MAX_CHARS=12000,
        ),
    )

    async def fake_budget(_db, _user):
        return None

    monkeypatch.setattr(intake_extraction_ai, "check_token_budget", fake_budget)

    class FakeDB:
        def add(self, _record):
            return None

        async def commit(self):
            return None

    class BrokenLLM:
        async def complete(self, **_kwargs):
            raise RuntimeError("provider down")

    with pytest.raises(intake_extraction_ai.IntakeExtractionUnavailable):
        await intake_extraction_ai.extract_with_ai(
            db=FakeDB(),
            user=SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4()),
            text="Case No.: 1",
            targets=[],
            document_sha256="a" * 64,
            llm=BrokenLLM(),
        )

    class BadJSONLLM:
        async def complete(self, **_kwargs):
            return ("not json", 1, 1)

    with pytest.raises(intake_extraction_ai.IntakeExtractionUnavailable):
        await intake_extraction_ai.extract_with_ai(
            db=FakeDB(),
            user=SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4()),
            text="Case No.: 1",
            targets=[],
            document_sha256="a" * 64,
            llm=BadJSONLLM(),
        )


def test_json_payload_strips_a_markdown_fence():
    fence = intake_extraction_ai._NO_MARKDOWN
    fenced = f"{fence}\n" + '{"values": []}\n' + fence
    assert intake_extraction_ai._json_payload(fenced) == '{"values": []}'


def test_ai_extraction_flag_is_separate_from_the_automatic_flag():
    assert extraction.ai_extraction_enabled(None) is False
    assert (
        extraction.ai_extraction_enabled(
            SimpleNamespace(custom_config={"intake_fact_extraction": {"enabled": True}})
        )
        is False
    )
    assert extraction.ai_extraction_enabled(
        SimpleNamespace(custom_config={"intake_fact_extraction": {"ai_enabled": True}})
    )


def test_ocr_line_candidates_pair_a_label_with_its_handwritten_value():
    target = standard_target("client.name", label="Client name")
    lines = [
        {"page_index": 0, "text": "Client name:", "score": 0.95, "rect": [72, 690, 150, 710]},
        {"page_index": 0, "text": "Ada Lovelace", "score": 0.61, "rect": [155, 690, 300, 710]},
        {"page_index": 1, "text": "Unrelated line", "score": 0.9, "rect": [72, 600, 300, 620]},
        {"page_index": 1, "text": "bad", "score": "x", "rect": [1]},
    ]
    found = extraction._ocr_line_candidates(lines, [target])
    (candidate,) = found["client.name"]
    assert candidate.value == "Ada Lovelace"
    assert candidate.source_kind == "ocr"
    assert candidate.source_locator.startswith("ocr:1:")
    # A pair is only as sure as its weaker read.
    assert candidate.confidence == pytest.approx(0.61)
    assert extraction._ocr_line_candidates([], [target]) == {}


def test_extract_candidates_attributes_ocr_text_to_the_scan():
    from app.services import document_text_cache as cache

    target = standard_target("client.name", label="Client name")
    scan = cache.Extraction(
        text="Client name: Ada Lovelace",
        engine=cache.ENGINE_OCR_LOCAL,
        ocr_confidence=0.7,
        lines=[],
    )
    found = extraction.extract_candidates(
        text=scan.text, form_values=[], targets=[target], extraction=scan
    )
    (candidate,) = found["client.name"]
    assert candidate.source_kind == "ocr" and candidate.confidence == pytest.approx(0.7)
    plain = extraction.extract_candidates(text=scan.text, form_values=[], targets=[target])
    assert plain["client.name"][0].source_kind == "label_value"
    assert plain["client.name"][0].confidence == 1.0


async def test_read_field_clip_sends_the_clip_and_meters_one_vision_call(monkeypatch):
    monkeypatch.setattr(
        intake_extraction_ai,
        "settings",
        SimpleNamespace(
            INTAKE_EXTRACTION_ENABLED=True,
            INTAKE_EXTRACTION_MODEL="lawhand-intake-extraction",
            INTAKE_EXTRACTION_VISION_MODEL="lawhand-intake-vision",
            INTAKE_EXTRACTION_INPUT_USD_PER_MILLION=0.30,
            INTAKE_EXTRACTION_OUTPUT_USD_PER_MILLION=1.20,
            INTAKE_EXTRACTION_MAX_CHARS=12000,
        ),
    )

    async def fake_budget(_db, _user):
        return None

    monkeypatch.setattr(intake_extraction_ai, "check_token_budget", fake_budget)
    seen: dict = {}

    class FakeLLM:
        async def complete(self, **kwargs):
            seen.update(kwargs)
            return ('{"value": "  Ada   Lovelace "}', 50, 5)

    added: list = []

    class FakeDB:
        def add(self, record):
            added.append(record)

        async def commit(self):
            return None

    value = await intake_extraction_ai.read_field_clip(
        db=FakeDB(),
        user=SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4(), tenant=None),
        png_bytes=b"\x89PNG fake",
        label="Client name",
        document_sha256="a" * 64,
        llm=FakeLLM(),
    )
    assert value == "Ada Lovelace"
    parts = seen["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "Field label: Client name"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert seen["model"] == "lawhand-intake-vision"
    assert seen["response_format"] == {"type": "json_object"}
    assert len(added) == 1
    assert added[0].operation_type == "intake_extraction_vision"
    assert added[0].requested_route == "intake-extraction-vision"
    assert added[0].model_used == "lawhand-intake-vision"

    class BlankLLM:
        async def complete(self, **_kwargs):
            return ('{"value": null}', 10, 2)

    assert (
        await intake_extraction_ai.read_field_clip(
            db=FakeDB(),
            user=SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4(), tenant=None),
            png_bytes=b"x",
            label="Notes",
            document_sha256="a" * 64,
            llm=BlankLLM(),
        )
        is None
    )


async def test_read_field_clip_is_closed_without_a_vision_model(monkeypatch):
    monkeypatch.setattr(
        intake_extraction_ai,
        "settings",
        SimpleNamespace(INTAKE_EXTRACTION_ENABLED=True, INTAKE_EXTRACTION_VISION_MODEL=""),
    )
    assert intake_extraction_ai.vision_enabled() is False
    with pytest.raises(intake_extraction_ai.IntakeExtractionUnavailable):
        await intake_extraction_ai.read_field_clip(
            db=None,
            user=SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4()),
            png_bytes=b"x",
            label="Client name",
            document_sha256="a" * 64,
        )
