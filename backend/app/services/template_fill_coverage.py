"""How much of a template fills itself from a matter.

Both visual editors already report *discovery* coverage — how many fields were
found and how many need review. Neither reported **fill** coverage: how many of
those fields arrive with a value when a matter is named, and how many are a box
somebody retypes on every matter. That number is the whole promise of document
automation, and until this module it existed nowhere in the product.

The classification here mirrors, branch for branch, the order
``build_variable_suggestions`` resolves a field in at fill time. It is a read
over the stored schema, never a second rule: if the two ever disagree the
read-out is lying, so the parity is asserted in
``tests/test_template_fill_coverage.py`` rather than left to review.

``_validate_approval_ready`` resolves fields through the same
``normalize_variable_name`` and ``binding_is_resolvable`` primitives, so the
read-out and the approval gate cannot disagree about whether a field has a
source. The gate deliberately keeps its own branch structure: it asks a
narrower question (can every *required* field be filled at all) and answering
it has consequences a read-out does not.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable

from app.services import template_cards
from app.services.template_bindings import (
    MANUAL_BINDING,
    custom_binding,
    declared_bindings,
    is_item_binding,
)

#: Fills from a record the matter carries. Survives a rename of the field.
BOUND = "bound"
#: No binding declared, but the field's name is one Smart Fill can produce.
#: Works today and stops working silently the moment the field is renamed,
#: which is why it is never folded into ``BOUND``.
NAME_MATCHED = "name_matched"
#: Declared ``manual``: always typed by hand, on purpose. Correct for an SSN.
MANUAL = "manual"
#: Signed rather than filled, so no data source applies.
SIGNATURE = "signature"
#: Declares a binding this catalogue can no longer resolve. Rare — the save
#: path validates paths — but it is the one state that fails silently at
#: render time, so it is reported on its own rather than as "no source".
UNRESOLVED = "unresolved"
#: Nothing behind it. Someone types this on every matter.
UNBOUND = "unbound"

#: The states that put a value on the page without anyone typing it.
FILLING_STATES = frozenset({BOUND, NAME_MATCHED})

_SIGNING_TYPES = frozenset({"signature", "initials"})


def normalize_variable_name(value: str) -> str:
    """Reduce a field name to the key Smart Fill's candidate map is built on."""

    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def is_signing_field(field: dict[str, Any]) -> bool:
    """Whether this field is signed rather than filled.

    A dated signature block is a ``date`` field carrying a signer role; an
    ordinary filled date has no role. This mirrors ``isSigningField`` in
    ``templateFillReview.js``, which the fill review already uses to keep
    signing fields out of its "how much is filled" rows.
    """

    field_type = str(field.get("field_type") or field.get("type") or "").lower()
    if field_type in _SIGNING_TYPES:
        return True
    return field_type == "date" and bool(str(field.get("signer_role") or "").strip())


def binding_is_resolvable(binding: str) -> bool:
    """Whether a declared binding path resolves against a record.

    Resolution goes through ``template_cards.alias_for_path``, the same
    resolver ``_bound_suggestion`` fills through. It has to: card paths are a
    superset of the flat catalogue, and the card rail is the control that
    produces most bindings, so asking ``template_bindings.alias_for_binding``
    alone would call ``client.full_name`` unresolvable while the fill resolves
    it to ``client_name`` without trouble. A read-out that disagrees with the
    fill is worse than no read-out.

    Item bindings resolve per repeating-section iteration and custom bindings
    through the custom-field service, so both fill without any alias at all.
    Manual bindings and paths the catalogue no longer describes cannot.

    A custom path is judged by its shape, not by looking the field up for the
    tenant: a custom field deleted out from under a template reads as bound
    here and fills blank at render. Approval makes the same assumption, and the
    read-out agreeing with the gate matters more than either being
    individually perfect.
    """

    if binding == MANUAL_BINDING:
        return False
    return (
        is_item_binding(binding)
        or custom_binding(binding) is not None
        or template_cards.alias_for_path(binding) is not None
    )


def field_has_source(
    *,
    binding: str | None,
    name: str,
    vocabulary: Iterable[str] | frozenset[str],
) -> bool:
    """Whether a field resolves to a data source.

    The one question both readers ask: ``classify_field`` of every field
    ("does it arrive with a value?") and the approval gate of every *required*
    field ("can this ever render a value?"). Answering it in one place means
    the state a field is coloured with and the verdict the gate reaches cannot
    drift: a field the gate accepts is never one the read-out calls unfilled.

    A declared binding is authoritative and never falls back to the name,
    exactly as in ``build_variable_suggestions`` at fill time. ``manual`` is
    not a source (``binding_is_resolvable`` reports it unresolved).
    """

    if binding:
        return binding_is_resolvable(binding)
    return normalize_variable_name(name) in vocabulary


def counts_toward_coverage(field: dict[str, Any]) -> bool:
    """Whether this field is one a matter has to supply a value for.

    Excluded fields are not in the template. A field that copies another
    ("use the same value as") is not separately answered, and counting it would
    report the same answer twice — the fill review drops these rows for the
    same reason.
    """

    if field.get("included", True) is False:
        return False
    if str(field.get("value_from") or "").strip():
        return False
    return bool(str(field.get("name") or "").strip())


def classify_field(
    field: dict[str, Any],
    *,
    binding: str | None,
    vocabulary: Iterable[str] | frozenset[str],
) -> str:
    """Return the fill state of one field.

    The branch order is ``build_variable_suggestions``'s own: a declared
    binding is authoritative and never falls back to name matching, because
    falling back is exactly the surprise bindings exist to remove.
    """

    if is_signing_field(field):
        return SIGNATURE
    if binding == MANUAL_BINDING:
        return MANUAL
    name = str(field.get("name") or "").strip()
    resolvable = field_has_source(binding=binding, name=name, vocabulary=vocabulary)
    if binding:
        return BOUND if resolvable else UNRESOLVED
    return NAME_MATCHED if resolvable else UNBOUND


@dataclass(frozen=True)
class FillCoverage:
    """The fill split of one template's fields.

    ``states`` is per field name so an editor can colour the page from the same
    read that produced the counts.
    """

    total: int
    counts: dict[str, int]
    states: dict[str, str]

    @property
    def fills(self) -> int:
        """Fields that arrive with a value when a matter is named."""

        return sum(self.counts.get(state, 0) for state in FILLING_STATES)


def coverage(
    variable_schema: dict | None,
    *,
    vocabulary: Iterable[str] | frozenset[str],
) -> FillCoverage:
    """Classify every field of ``variable_schema`` by where its value comes from."""

    vocabulary = frozenset(vocabulary)
    fields = (
        variable_schema.get("fields") if isinstance(variable_schema, dict) else None
    )
    if not isinstance(fields, list):
        fields = []
    bindings = declared_bindings(variable_schema)
    counts = {
        state: 0
        for state in (BOUND, NAME_MATCHED, MANUAL, SIGNATURE, UNRESOLVED, UNBOUND)
    }
    states: dict[str, str] = {}
    for field in fields:
        if not isinstance(field, dict) or not counts_toward_coverage(field):
            continue
        name = str(field.get("name") or "").strip()
        state = classify_field(field, binding=bindings.get(name), vocabulary=vocabulary)
        states[name] = state
        counts[state] += 1
    return FillCoverage(total=len(states), counts=counts, states=states)
