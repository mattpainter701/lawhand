"""Bounded parsing and hardening for CSV files staff upload or download."""

from __future__ import annotations

import csv
import io

#: Leading characters a spreadsheet treats as the start of a formula. Tab and
#: carriage return belong here alongside the obvious four: Excel and LibreOffice
#: strip them during cell parsing and evaluate whatever follows.
CSV_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value) -> str:
    """Neutralise a cell so a spreadsheet shows it rather than evaluating it."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(CSV_FORMULA_LEADS) else text


def read_csv_rows(
    raw: bytes, *, max_bytes: int, max_rows: int, label: str = "CSV"
) -> tuple[list[str], list[dict[str, str]]]:
    """Decode and read a bounded CSV into header names and stripped rows.

    Header names are lower-cased and stripped so ``Matter Name`` and
    ``matter_name `` both reach the caller as ``matter_name``; every cell is
    stripped. Raises ``ValueError`` with a message fit for the client on any
    bound or encoding problem, so the caller decides the HTTP status.
    """
    if not raw:
        raise ValueError(f"The {label} is empty")
    if len(raw) > max_bytes:
        raise ValueError(
            f"The {label} exceeds the {max_bytes // (1024 * 1024)} MiB limit"
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"The {label} must be UTF-8 encoded") from exc
    try:
        reader = csv.DictReader(io.StringIO(text))
        headers = [
            (header or "").strip().lower().replace(" ", "_")
            for header in (reader.fieldnames or [])
        ]
        if not headers or not any(headers):
            raise ValueError(f"The {label} is missing a header row")
        if len(headers) > 100 or len(set(headers)) != len(headers):
            raise ValueError(f"{label} headers must be unique (at most 100)")
        rows: list[dict[str, str]] = []
        for row in reader:
            if len(rows) >= max_rows:
                raise ValueError(f"The {label} exceeds the {max_rows:,}-row limit")
            if None in row:
                raise ValueError(
                    f"{label} row {len(rows) + 2} has more values than its header"
                )
            cleaned = {
                (key or "").strip().lower().replace(" ", "_"): (value or "").strip()
                for key, value in row.items()
            }
            # A wholly blank line is a spreadsheet artefact, not a record.
            if not any(cleaned.values()):
                rows.append({})
                continue
            rows.append(cleaned)
    except csv.Error as exc:
        raise ValueError(f"The {label} could not be parsed") from exc
    return headers, rows
