"""Jurisdiction registry: maps a state to its :class:`ProbateJurisdiction`.

Mirrors ``app.services.childsupport.registry``. Adding a state is one module
under ``jurisdictions/`` plus one row below; the workbench, the ``estate.*``
Smart Fill bindings, and the storage never change. North Dakota is the only
registered implementation today.
"""

from __future__ import annotations

from app.services.probate.base import ProbateJurisdiction
from app.services.probate.jurisdictions.north_dakota import NORTH_DAKOTA

DEFAULT_CODE = "ND"

# state_code -> jurisdiction. Extend as states land.
_JURISDICTIONS: dict[str, ProbateJurisdiction] = {
    NORTH_DAKOTA.code: NORTH_DAKOTA,
}

# USPS code -> full name, for normalising the estate's free-text ``jurisdiction``
# field ("North Dakota", "ND", "n.d.") to a code. Anything that is not a state
# is left unrecognised so the caller can fall back to the default.
_STATE_NAME_TO_CODE: dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}
_STATE_CODES = frozenset(_STATE_NAME_TO_CODE.values())
_CODE_ALIASES = {"n.d.": "ND", "n dakota": "ND", "no. dakota": "ND"}


class UnsupportedJurisdictionError(ValueError):
    """Raised when an explicit jurisdiction has no registered implementation."""


def normalize(value: object) -> str | None:
    """A USPS code for a recognised US state, else ``None``.

    ``None`` is returned for blank and for free text that is not a state (a
    county name, say); callers decide whether that means "use the default" or
    "ask the user". An explicit, recognised state that is not registered is
    returned as its code so the caller can fail closed.
    """

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = " ".join(text.lower().split())
    if lowered in _CODE_ALIASES:
        return _CODE_ALIASES[lowered]
    if lowered in _STATE_NAME_TO_CODE:
        return _STATE_NAME_TO_CODE[lowered]
    upper = text.upper()
    if len(upper) == 2 and upper in _STATE_CODES:
        return upper
    return None


def get(code: str | None) -> ProbateJurisdiction | None:
    """The registered jurisdiction for a code, or ``None``."""

    if not code:
        return None
    return _JURISDICTIONS.get(str(code).strip().upper())


def require(code: str | None) -> ProbateJurisdiction:
    """The jurisdiction for a code or raise ``UnsupportedJurisdictionError``."""

    bundle = get(code)
    if bundle is None:
        raise UnsupportedJurisdictionError(
            f"Probate is not yet supported for jurisdiction '{code}'."
        )
    return bundle


def default() -> ProbateJurisdiction:
    return _JURISDICTIONS[DEFAULT_CODE]


def for_estate(estate) -> ProbateJurisdiction | None:
    """Resolve the estate's jurisdiction.

    Blank or unrecognised free text (the estate's ``jurisdiction`` field is
    free-form) falls back to the default. An explicitly recognised state with no
    implementation returns ``None`` so the caller fails closed instead of
    applying North Dakota law to, say, a Minnesota estate.
    """

    code = normalize(getattr(estate, "jurisdiction", None))
    if code is None:
        return default()
    return get(code)


def supported_codes() -> set[str]:
    return set(_JURISDICTIONS)


def list_jurisdictions() -> list[dict[str, str]]:
    """Catalog of supported jurisdictions for the frontend selector."""

    return [
        {"code": bundle.code, "name": bundle.name, "label": bundle.name}
        for bundle in sorted(_JURISDICTIONS.values(), key=lambda item: item.name)
    ]
