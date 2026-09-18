"""North Dakota: the first :class:`ProbateJurisdiction` implementation.

The ND rules already live in ``determination.py``, ``deadlines.py``, and
``forms.py``; this module binds them into the bundle the workbench resolves,
so those modules stay the readable, testable ND tables they are. A second state
adds a sibling module and a registry row rather than editing this one.
"""

from __future__ import annotations

from app.services.practice_resolution import PROBATE_QUESTIONS
from app.services.probate import deadlines, determination, forms
from app.services.probate.base import ProbateJurisdiction

NORTH_DAKOTA = ProbateJurisdiction(
    code="ND",
    name="North Dakota",
    statute_label="N.D.C.C.",
    questions=PROBATE_QUESTIONS,
    determine=determination.determine,
    formal_checklist=forms.formal_checklist,
    deadline_rules=deadlines.RULES,
    deadline_rule_types=deadlines.RULE_TYPES,
    forms=forms.ND_PROBATE_FORMS,
    guidebook_slug=forms.GUIDEBOOK_SLUG,
    pack_samples=forms.PACK_SAMPLES,
)
