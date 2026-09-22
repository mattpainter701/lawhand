"""Print the Smart Fill quirk report over mock matters and mock documents.

Runs the same campaign the tests pin (``tests/fill_campaign``) and writes a
Markdown table plus JSON to ``--out``.  Nothing touches a database unless
``--db`` is given, and then only the disposable test database named by
``TEST_DATABASE_URL``.

    python scripts/rehearse_smart_fill.py --out build/quirks
    python scripts/rehearse_smart_fill.py --seed-pdfs --out build/quirks
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


from tests.fill_campaign import documents, report, runner, scenarios  # noqa: E402


def _cases() -> list[tuple[str, dict, bytes, str]]:
    pdf = documents.convention_pdf()
    docx, names = documents.convention_docx()
    return [
        ("convention.pdf (unbound)", documents.schema_for_pdf(pdf), pdf, "pdf"),
        (
            "convention.pdf (bound)",
            documents.schema_for_pdf(pdf, bindings=documents.CONVENTION_BINDINGS),
            pdf,
            "pdf",
        ),
        ("convention.docx (unbound)", documents.schema_for_docx(names), docx, "docx"),
        (
            "convention.docx (bound)",
            documents.schema_for_docx(names, bindings=documents.DOCX_BINDINGS),
            docx,
            "docx",
        ),
    ]


async def _run(seed_pdfs: bool) -> list[runner.CaseResult]:
    results: list[runner.CaseResult] = []
    cases = _cases()
    for scenario in scenarios.all_scenarios():
        for document, schema, source, fmt in cases:
            results.append(
                await runner.run_case(
                    scenario, document=document, schema=schema, source=source, fmt=fmt
                )
            )
    if seed_pdfs:
        for form in documents.seed_forms_with_bindings():
            source = documents.seed_pdf(form)
            schema = documents.schema_for_pdf(source, bindings=form["bindings"])
            scenario = (
                scenarios.probate_estate()
                if form["slug"] == "nd-informal-probate-guidebook"
                else scenarios.individual_client()
            )
            results.append(
                await runner.run_case(
                    scenario,
                    document=f"seed:{form['slug']}",
                    schema=schema,
                    source=source,
                    fmt="pdf",
                )
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--seed-pdfs",
        action="store_true",
        help="also run the seeded sample forms that ship bindings",
    )
    args = parser.parse_args()
    results = asyncio.run(_run(args.seed_pdfs))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "smart_fill_quirks.md").write_text(report.render_markdown(results))
    (args.out / "smart_fill_quirks.json").write_text(report.render_json(results))
    rows = report.rows(results)
    filled = sum(1 for row in rows if row["state"] == runner.FILLED)
    blank = sum(1 for row in rows if row["state"] == runner.BLANK)
    print(
        f"{len(results)} cases, {len(rows)} field outcomes: {filled} filled, "
        f"{blank} blank, {sum(len(r.errors) for r in results)} render errors, "
        f"{sum(len(r.collisions) for r in results)} alias collisions."
    )
    print(f"Report: {args.out / 'smart_fill_quirks.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
