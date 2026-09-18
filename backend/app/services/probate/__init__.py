"""Probate administration for the Trust, Estate & Probate add-on.

Everything probate-specific lives in this package behind one constant so the
work can be resold as its own add-on later by changing ``PROBATE_ADDON`` and a
manifest entry, never the data or the screens.

The package is deliberately pure where it can be: ``facts`` and
``determination`` never touch the database, so the rules that decide which
North Dakota proceeding an estate needs are testable as a table.
"""

from app.services.practice_resolution import PROBATE_QUESTIONS

#: The add-on entitlement every probate surface is gated behind.
PROBATE_ADDON = "trust-estate-legal"

#: Question keys the probate intake asks, in the order the client sees them.
PROBATE_QUESTION_KEYS: tuple[str, ...] = tuple(q.key for q in PROBATE_QUESTIONS)

__all__ = ["PROBATE_ADDON", "PROBATE_QUESTION_KEYS"]
