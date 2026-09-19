from __future__ import annotations

import io

from docx import Document

from app.services.cloud_artifact_materialization import (
    canonical_docx_filename,
    render_revision_docx,
)


def test_canonical_docx_filename_is_safe_and_deterministic() -> None:
    value = canonical_docx_filename(
        "  Client / privileged: memo?.docx  ", revision_no=3
    )
    assert value == "Client - privileged- memo-r3.docx"
    assert "/" not in value and "?" not in value
    assert value.endswith(".docx")


def test_renderer_emits_valid_docx_and_preserves_paragraphs() -> None:
    raw = render_revision_docx(
        title="Review memo", content="First paragraph\nSecond paragraph"
    )
    assert raw.startswith(b"PK")
    document = Document(io.BytesIO(raw))
    assert document.core_properties.title == "Review memo"
    assert [p.text for p in document.paragraphs][-2:] == [
        "First paragraph",
        "Second paragraph",
    ]


def test_renderer_strips_xml_illegal_control_characters() -> None:
    raw = render_revision_docx(title="Draft", content="safe\x00 text")
    document = Document(io.BytesIO(raw))
    assert "safe text" in [p.text for p in document.paragraphs]


def test_renderer_parses_markdown_structure_and_inline_emphasis() -> None:
    raw = render_revision_docx(
        title="Motion",
        content=(
            "## ARGUMENT\n"
            "**Bold point** and *italic* text\n"
            "- first item\n"
            "- second item\n"
            "1. numbered\n"
            "> quoted line\n"
            "\n"
            "```\n"
            "code line\n"
            "```\n"
            "| H1 | H2 |\n"
            "| --- | --- |\n"
            "| a | b |\n"
        ),
    )
    document = Document(io.BytesIO(raw))
    paragraphs = document.paragraphs

    heading = next(p for p in paragraphs if p.style.name == "Heading 2")
    assert heading.text == "ARGUMENT"

    emphasized = next(
        p for p in paragraphs if p.text == "Bold point and italic text"
    )
    assert any(run.bold for run in emphasized.runs)
    assert any(run.italic for run in emphasized.runs)

    bullets = [p for p in paragraphs if p.style.name == "List Bullet"]
    assert [p.text for p in bullets] == ["first item", "second item"]

    numbered = [p for p in paragraphs if p.style.name == "List Number"]
    assert [p.text for p in numbered] == ["numbered"]

    quote = next(p for p in paragraphs if p.style.name == "Quote")
    assert quote.text == "quoted line"

    code = next(p for p in paragraphs if p.text == "code line")
    assert code.runs[0].font.name == "Consolas"

    assert len(document.tables) == 1
    assert [cell.text for cell in document.tables[0].rows[0].cells] == ["H1", "H2"]
    assert [cell.text for cell in document.tables[0].rows[1].cells] == ["a", "b"]

    # Blank lines are separators, not materialized empty paragraphs.
    assert "" not in [p.text for p in paragraphs]
