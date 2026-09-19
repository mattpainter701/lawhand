"""Shape a suggested value to the field that will hold it.

Smart Fill's candidates are the record's raw text: a ``Decimal`` prints as
``250.00``, a date as ``2026-03-04``, a state as ``ND``. A text field takes
that as it is and the author formats the template around it. Three field
types cannot: a **choice** or **radio** widget only accepts one of its export
values, a **checkbox** only ``true``/``false``, and a **date** field is
expected to read the way a form prints one. This module makes those three
conversions and no other, and says so in the provenance when it does.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.schemas.document_template import DocumentTemplateVariableSuggestion

_TRUE = frozenset({"true", "yes", "y", "1", "x", "on", "checked"})
_FALSE = frozenset({"false", "no", "n", "0", "off", "unchecked", ""})

#: USPS state and territory codes, so a contact's ``ND`` can select the
#: ``North Dakota`` option of a court form and vice versa.
US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands",
}  # fmt: skip
_STATE_BY_NAME = {name.casefold(): code for code, name in US_STATES.items()}

DATE_FORMAT = "%m/%d/%Y"
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ].*)?$")


def field_type(spec: dict[str, Any]) -> str:
    return str(spec.get("field_type") or spec.get("type") or "text").strip().lower()


def _options(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """``(export value, label)`` pairs, from either option shape."""

    pairs: list[tuple[str, str]] = []
    for option in spec.get("options") or []:
        if isinstance(option, dict):
            value = str(option.get("value") or "")
            label = str(option.get("label") or value)
        else:
            value = label = str(option)
        if value:
            pairs.append((value, label))
    return pairs


def _equivalents(value: str) -> set[str]:
    """Spellings a value may be matched under: itself and its state name/code."""

    text = value.strip()
    folded = text.casefold()
    forms = {folded}
    if text.upper() in US_STATES:
        forms.add(US_STATES[text.upper()].casefold())
    if folded in _STATE_BY_NAME:
        forms.add(_STATE_BY_NAME[folded].casefold())
    return forms


def choice_value(value: str, spec: dict[str, Any]) -> str | None:
    """The export value the widget accepts for ``value``, or ``None``.

    An exact export value passes through. Otherwise the option is chosen by
    label or export value, ignoring case, and a US state may be given by code
    or by name whichever way the form lists it. Anything else is left to the
    person: a wrong guess on a form is worse than a blank.
    """

    options = _options(spec)
    if not options:
        return value
    for export, _label in options:
        if export == value:
            return value
    wanted = _equivalents(value)
    for export, label in options:
        if _equivalents(export) & wanted or _equivalents(label) & wanted:
            return export
    return None


def checkbox_value(value: str) -> str | None:
    folded = value.strip().casefold()
    if folded in _TRUE:
        return "true"
    if folded in _FALSE:
        return "false"
    return None


def date_value(value: str, fmt: str = DATE_FORMAT) -> str | None:
    """``MM/DD/YYYY`` for an ISO date; anything already human stays as is."""

    text = value.strip()
    if not _ISO_DATE.match(text):
        return text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.strftime(fmt)


def format_value(value: str, spec: dict[str, Any]) -> tuple[str | None, str | None]:
    """``(formatted value, note)``. ``None`` means the field cannot take it."""

    kind = field_type(spec)
    if kind in ("choice", "radio"):
        chosen = choice_value(value, spec)
        if chosen is None:
            return None, f"{value!r} is not one of this field's options"
        return chosen, None if chosen == value else "matched to an option"
    if kind == "checkbox":
        chosen = checkbox_value(value)
        if chosen is None:
            return None, f"{value!r} is not a checkbox value"
        return chosen, None if chosen == value else "read as a checkbox"
    if kind == "date":
        chosen = date_value(value)
        if chosen is None:
            return None, f"{value!r} is not a date"
        return chosen, None if chosen == value else "formatted as a date"
    return value, None


def format_suggestion(
    suggestion: DocumentTemplateVariableSuggestion, spec: dict[str, Any] | None
) -> DocumentTemplateVariableSuggestion:
    """Return ``suggestion`` shaped for ``spec``, recording any change.

    A value the field cannot hold is withdrawn -- the suggestion keeps its
    provenance, gains ``format_warning``, and asks for review -- rather than
    pushed into a widget that would reject or misread it.
    """

    if not spec or suggestion.suggested_value in (None, ""):
        return suggestion
    raw = str(suggestion.suggested_value)
    formatted, note = format_value(raw, spec)
    if formatted == raw:
        return suggestion
    if formatted is None:
        return suggestion.model_copy(
            update={
                "suggested_value": None,
                "review_required": True,
                "provenance": {
                    **suggestion.provenance,
                    "format_warning": note,
                    "unformatted_value": raw,
                },
            }
        )
    return suggestion.model_copy(
        update={
            "suggested_value": formatted,
            "provenance": {
                **suggestion.provenance,
                "formatted_from": raw,
                "format_note": note,
            },
        }
    )


def as_text(value: Any) -> str | None:
    """A date or datetime as the form-style text the date formatter emits."""

    if isinstance(value, datetime):
        return value.strftime(DATE_FORMAT)
    if isinstance(value, date):
        return value.strftime(DATE_FORMAT)
    return None
