"""The facts a probate determination is made from.

``ProbateFacts`` is the structured form of the probate intake: what the
client answered, what staff typed in over the phone, and what an attorney
corrected. It is stored as JSON on the estate (``estates.probate_facts``) and
read back into this dataclass before any rule runs, so the rules never parse
free text themselves.

Parsing is tolerant on purpose. The same questions arrive from a portal form
(ISO dates, ``yes``/``no``), from a returned fillable PDF (whatever a person
typed, radio export values), and from a staff member reading a mailed paper
copy. A value that cannot be read becomes ``None`` — an unknown, never a
guess — and the determination reports it as a missing fact.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

_TRUE = {"yes", "y", "true", "1", "on", "checked", "x"}
_FALSE = {"no", "n", "false", "0", "off", "unchecked", "none"}
_DATE_PATTERNS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%B %d, %Y",
    "%b %d, %Y",
)
_MONEY_STRIP = re.compile(r"[,$\s]")


@dataclass(frozen=True)
class HeirRow:
    """One line of the surviving spouse / children / heirs / devisees table."""

    name: str
    age: str = ""
    relationship: str = ""
    address: str = ""

    def as_line(self) -> str:
        parts = [self.name, self.age, self.relationship, self.address]
        return " — ".join(part for part in parts if part)


@dataclass(frozen=True)
class ProbateFacts:
    """Every fact the North Dakota informal-probate rules and forms consume."""

    decedent_name: str | None = None
    decedent_aka: str | None = None
    date_of_death: date | None = None
    date_of_birth: date | None = None
    age_at_death: int | None = None
    domicile_state: str | None = None
    domicile_county: str | None = None
    real_property_in_nd: bool | None = None
    nd_property_counties: tuple[str, ...] = ()
    probate_property_value: Decimal | None = None
    will_exists: bool | None = None
    will_original_available: bool | None = None
    will_execution_date: date | None = None
    applicant_name: str | None = None
    applicant_relationship: str | None = None
    applicant_is_nominee: bool | None = None
    applicant_address: str | None = None
    applicant_phone: str | None = None
    applicant_email: str | None = None
    persons_with_prior_or_equal_priority: tuple[str, ...] = ()
    heirs: tuple[HeirRow, ...] = ()
    probate_opened_elsewhere: bool | None = None
    prior_appointment: bool | None = None
    prior_appointment_details: str | None = None
    demand_for_notice: bool | None = None
    demand_for_notice_details: str | None = None
    bond_amount: Decimal | None = None
    assets_summary: str | None = None
    debts_summary: str | None = None
    funeral_expenses: Decimal | None = None
    #: Staff-only switch that opens the portal inventory before appointment.
    inventory_open: bool = False
    #: Free-form attorney notes kept with the facts, never printed on a form.
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def computed_age_at_death(self) -> int | None:
        if self.age_at_death is not None:
            return self.age_at_death
        if self.date_of_birth is None or self.date_of_death is None:
            return None
        years = self.date_of_death.year - self.date_of_birth.year
        if (self.date_of_death.month, self.date_of_death.day) < (
            self.date_of_birth.month,
            self.date_of_birth.day,
        ):
            years -= 1
        return years if years >= 0 else None

    def is_nd_domicile(self) -> bool | None:
        if not self.domicile_state:
            return None
        return _state_code(self.domicile_state) == "ND"


# ── Parsers ───────────────────────────────────────────────────────────────────


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for pattern in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def parse_money(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if value is None:
        return None
    text = _MONEY_STRIP.sub("", str(value))
    if not text:
        return None
    # "about 80k", "$1.2M" — a client's rough answer is still an answer.
    multiplier = Decimal(1)
    lowered = text.lower().rstrip(".")
    if lowered.endswith("k"):
        multiplier, lowered = Decimal(1000), lowered[:-1]
    elif lowered.endswith("m"):
        multiplier, lowered = Decimal(1_000_000), lowered[:-1]
    lowered = re.sub(r"^(about|approx|approximately|roughly|~)", "", lowered)
    try:
        return (Decimal(lowered) * multiplier).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    text = re.sub(r"[^0-9]", "", str(value))
    return int(text) if text else None


def parse_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value]
    else:
        items = re.split(r"[\n;,]+", str(value))
    cleaned = tuple(item.strip() for item in items if item and item.strip())
    if len(cleaned) == 1 and cleaned[0].lower() in {"none", "n/a", "na", "no"}:
        return ()
    return cleaned


def parse_heirs(value: Any) -> tuple[HeirRow, ...]:
    """Read the heirs table from structured rows or one-person-per-line text.

    A line may separate the columns with ``;``, ``|``, a tab, or `` — ``; a
    plain sentence becomes a row with only a name, which the attorney completes
    on the Probate tab.
    """

    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        rows = []
        for item in value:
            if isinstance(item, HeirRow):
                rows.append(item)
            elif isinstance(item, Mapping):
                name = str(item.get("name") or "").strip()
                if name:
                    rows.append(
                        HeirRow(
                            name=name,
                            age=str(item.get("age") or "").strip(),
                            relationship=str(item.get("relationship") or "").strip(),
                            address=str(item.get("address") or "").strip(),
                        )
                    )
            elif str(item).strip():
                rows.extend(parse_heirs(str(item)))
        return tuple(rows)
    rows = []
    for line in str(value).splitlines():
        line = line.strip(" \t-•*")
        if not line or line.lower() in {"none", "n/a"}:
            continue
        parts = [part.strip() for part in re.split(r"\s*(?:;|\||\t| — | – )\s*", line)]
        parts = [part for part in parts if part]
        if not parts:
            continue
        rows.append(
            HeirRow(
                name=parts[0],
                age=parts[1] if len(parts) > 1 else "",
                relationship=parts[2] if len(parts) > 2 else "",
                address=" ".join(parts[3:]) if len(parts) > 3 else "",
            )
        )
    return tuple(rows)


_STATE_CODES = {
    "nd": "ND",
    "n.d.": "ND",
    "north dakota": "ND",
    "mn": "MN",
    "minnesota": "MN",
    "sd": "SD",
    "south dakota": "SD",
    "mt": "MT",
    "montana": "MT",
}


def _state_code(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().lower()
    if text in _STATE_CODES:
        return _STATE_CODES[text]
    return text.upper() if len(text) == 2 else text.title()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


# ── JSON round trip ───────────────────────────────────────────────────────────

_DATE_FIELDS = ("date_of_death", "date_of_birth", "will_execution_date")
_BOOL_FIELDS = (
    "real_property_in_nd",
    "will_exists",
    "will_original_available",
    "applicant_is_nominee",
    "probate_opened_elsewhere",
    "prior_appointment",
    "demand_for_notice",
)
_MONEY_FIELDS = ("probate_property_value", "bond_amount", "funeral_expenses")
_LIST_FIELDS = ("nd_property_counties", "persons_with_prior_or_equal_priority")
_KNOWN_FIELDS = {item.name for item in fields(ProbateFacts)}


def from_json(data: Mapping[str, Any] | None) -> ProbateFacts:
    """Build facts from stored JSON or from a loosely typed input payload."""

    if not data:
        return ProbateFacts()
    values: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for key, raw in data.items():
        if key == "extra" and isinstance(raw, Mapping):
            extra.update(raw)
            continue
        if key not in _KNOWN_FIELDS:
            extra[key] = raw
            continue
        if key in _DATE_FIELDS:
            values[key] = parse_date(raw)
        elif key in _BOOL_FIELDS:
            values[key] = parse_bool(raw)
        elif key in _MONEY_FIELDS:
            values[key] = parse_money(raw)
        elif key in _LIST_FIELDS:
            values[key] = parse_list(raw)
        elif key == "heirs":
            values[key] = parse_heirs(raw)
        elif key == "age_at_death":
            values[key] = parse_int(raw)
        elif key == "inventory_open":
            values[key] = bool(parse_bool(raw))
        else:
            values[key] = _text(raw)
    return ProbateFacts(**values, extra=extra)


def to_json(facts: ProbateFacts) -> dict[str, Any]:
    """Serialise for the JSONB column: ISO dates, decimal strings, plain lists."""

    data = asdict(facts)
    for key in _DATE_FIELDS:
        data[key] = data[key].isoformat() if data[key] else None
    for key in _MONEY_FIELDS:
        data[key] = str(data[key]) if data[key] is not None else None
    for key in _LIST_FIELDS:
        data[key] = list(data[key])
    data["heirs"] = [dict(row) for row in data["heirs"]]
    return data


def merge(
    base: ProbateFacts, incoming: ProbateFacts, *, overwrite: bool = False
) -> ProbateFacts:
    """Fill gaps in ``base`` from ``incoming``; replace everything when asked.

    The default never discards what an attorney already corrected: an answer
    from a second questionnaire only lands where the estate had nothing.
    """

    changes: dict[str, Any] = {}
    for item in fields(ProbateFacts):
        if item.name == "extra":
            merged = dict(base.extra)
            for key, value in incoming.extra.items():
                if overwrite or key not in merged:
                    merged[key] = value
            changes["extra"] = merged
            continue
        current = getattr(base, item.name)
        new = getattr(incoming, item.name)
        empty = (
            new is None
            or new == ()
            or new == ""
            or (item.name == "inventory_open" and new is False)
        )
        if empty:
            continue
        if overwrite or current is None or current == () or current == "":
            changes[item.name] = new
    return replace(base, **changes)


def is_blank(facts: ProbateFacts) -> bool:
    return to_json(facts) == to_json(ProbateFacts())
