"""The contract every state's probate rules satisfy.

The workbench (routers, Smart Fill bindings, deadline clock) never imports a
state's rules directly. It resolves a :class:`ProbateJurisdiction` for the
estate and asks that bundle to determine the track, list the court forms, and
compute the deadlines. Adding a state is therefore a new module under
``jurisdictions/`` plus one registry entry — the shared screens, storage, and
``estate.*`` bindings do not change.

The bundle deliberately carries *data and pure functions*, not ORM rows, so it
can be unit-tested without a database and a second state can encode its own
filing labels and statutes without touching ``determination.py``'s ND tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

from app.services.practice_resolution import PackQuestion


class FormRow(Protocol):
    """The subset of a jurisdiction's form registry the workbench reads."""

    number: int
    title: str
    phase: str
    pages: tuple[int, int]
    tracks: frozenset[str]
    optional: bool
    statute: str


@dataclass(frozen=True)
class ProbateJurisdiction:
    """One state's probate law, as the workbench consumes it."""

    code: str  # e.g. "ND"
    name: str  # e.g. "North Dakota"
    statute_label: str  # e.g. "N.D.C.C." — prefixes every citation
    questions: tuple[PackQuestion, ...]
    #: Pure ``facts -> ProbateDetermination`` function.
    determine: Callable[[Any], Any]
    #: Pure ``track -> tuple[dict, ...]`` for formal-proceeding slots.
    formal_checklist: Callable[[str | None], Sequence[dict]]
    #: ``DeadlineRule`` tuples; ``deadlines.compute`` consumes these.
    deadline_rules: tuple[Any, ...]
    deadline_rule_types: tuple[str, ...]
    #: The state's form registry (objects shaped like ``FormRow``).
    forms: tuple[Any, ...]
    guidebook_slug: str | None
    #: ``(slug, kind, description)`` samples installed into a firm.
    pack_samples: tuple[tuple[str, str, str], ...]

    def forms_for(self, track: str | None) -> tuple[Any, ...]:
        """Required (non-optional) forms for a track, in filing order."""

        if not track:
            return ()
        return tuple(
            item for item in self.forms if track in item.tracks and not item.optional
        )

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "number": item.number,
                "key": f"form_{item.number:02d}",
                "title": item.title,
                "phase": item.phase,
                "pages": list(item.pages),
                "tracks": sorted(item.tracks),
                "optional": item.optional,
                "statute": item.statute,
            }
            for item in self.forms
        ]
