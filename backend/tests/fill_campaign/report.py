"""Render campaign results as Markdown and JSON."""

from __future__ import annotations

import json
from typing import Iterable

from .runner import CaseResult

COLUMNS = (
    "scenario",
    "document",
    "field",
    "state",
    "coverage",
    "source",
    "value",
    "note",
)


def rows(results: Iterable[CaseResult]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for result in results:
        for outcome in result.outcomes:
            output.append(
                {
                    "scenario": result.scenario,
                    "document": result.document,
                    "field": outcome.name,
                    "state": outcome.state,
                    "coverage": outcome.coverage_state or "",
                    "source": outcome.source_type or "",
                    "value": outcome.value or "",
                    "note": outcome.note or "",
                }
            )
    return output


def render_json(results: Iterable[CaseResult]) -> str:
    results = list(results)
    payload = {
        "rows": rows(results),
        "collisions": [
            {"scenario": r.scenario, "document": r.document, **c}
            for r in results
            for c in r.collisions
        ],
        "errors": [
            {"scenario": r.scenario, "document": r.document, "error": e}
            for r in results
            for e in r.errors
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(results: Iterable[CaseResult]) -> str:
    results = list(results)
    lines = ["# Smart Fill quirk report", ""]
    table = rows(results)
    filled = sum(1 for row in table if row["state"] == "filled")
    blank = sum(1 for row in table if row["state"] == "blank")
    lying = sum(
        1
        for row in table
        if row["state"] == "blank" and row["coverage"] in ("bound", "name_matched")
    )
    lines.append(
        f"{len(table)} field outcomes across {len(results)} cases: "
        f"{filled} filled, {blank} blank. Coverage predicted a value for {lying} of "
        "the blanks; the note column says whether the record was absent or the "
        "resolver could not reach it."
    )
    lines.append("")
    lines.append("| " + " | ".join(COLUMNS) + " |")
    lines.append("|" + "---|" * len(COLUMNS))
    for row in table:
        lines.append("| " + " | ".join(_cell(row[column]) for column in COLUMNS) + " |")
    # A collision is a property of the scenario, not of the document it was
    # observed through, so report each (scenario, alias) once.
    seen: set[tuple[str, str]] = set()
    collisions = []
    for r in results:
        for c in r.collisions:
            if (r.scenario, c["alias"]) in seen:
                continue
            seen.add((r.scenario, c["alias"]))
            collisions.append((r, c))
    if collisions:
        lines += ["", "## Alias collisions (first writer wins silently)", ""]
        lines.append("| scenario | alias | winner | losers |")
        lines.append("|---|---|---|---|")
        for result, collision in collisions:
            losers = "; ".join(
                f"{loser['source_type']}={loser['value']}"
                for loser in collision["losers"]
            )
            lines.append(
                f"| {result.scenario} | {collision['alias']} | "
                f"{_cell(collision['winner']['source_type'] + '=' + collision['winner']['value'])} | {_cell(losers)} |"
            )
    errors = [(r, e) for r in results for e in r.errors]
    if errors:
        lines += ["", "## Render errors", ""]
        for result, error in errors:
            lines.append(f"- {result.scenario} / {result.document}: {_cell(error)}")
    return "\n".join(lines) + "\n"
