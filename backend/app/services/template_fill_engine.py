"""The Smart Fill engine: resolve a template's fields from matter data.

Before this module the resolver lived inside the templates router as one
function that built a flat ``{alias: suggestion}`` dictionary from a fixed
sequence of record reads. That dictionary is still the contract -- a declared
binding resolves to an alias, and an unbound field matches an alias by name --
but the pieces are now explicit:

* a :class:`FillSource` declares the aliases it can produce, whether a given
  template needs it loaded at all, and how its record turns into candidates;
* :data:`SOURCES` is the ordered registry. Order matters: the first source to
  write an alias wins, exactly as before, and the losing writes are now kept
  as :class:`Collision` records instead of vanishing;
* :func:`vocabulary` is the union of what the sources declare. The approval
  gate used to learn it by running the resolver over a fabricated matter; a
  test now proves the declaration and that probe agree;
* :func:`prepare_fill` runs the whole thing for a template and a matter and
  returns a :class:`PreparedFill` -- suggestions, render-ready values, the
  coverage split and the unfilled required fields -- without needing a request
  or a signed-in user, which is what lets a job prepare documents the moment a
  matter has data.

Behaviour is unchanged from the router with one deliberate exception: a source
is loaded when a field *name* matches one of its aliases, not only when a
binding does. The estate used to load only for an ``estate.`` binding, so an
unbound field named ``estate_decedent_name`` was reported as filling by the
coverage read-out and rendered blank.
"""

from __future__ import annotations

import functools
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.schemas.document_template import DocumentTemplateVariableSuggestion
from app.schemas.matter_party import normalize_matter_party_role
from app.services import (
    template_cards,
    template_custom_fields,
    template_fill_formatters,
    template_firm_fields,
)
from app.services.probate import bindings as probate_bindings
from app.services.template_bindings import (
    MANUAL_BINDING,
    declared_bindings,
    is_item_binding,
)
from app.services.template_cards import CardKind
from app.services.template_fill_coverage import (
    FillCoverage,
    coverage as fill_coverage,
    is_signing_field,
    normalize_variable_name,
)
from app.services.template_fill_loaders import DEFAULT_LOADERS, Loaders

VARIABLE_PATTERN = re.compile(r"\{\{(.+?)\}\}")


# --------------------------------------------------------------------------
# Template variables
# --------------------------------------------------------------------------


def extract_template_variables(template_body: str) -> list[str]:
    """Return the substitutable variables in a body, in first-seen order.

    Logic markers (``{{#if x}}``, ``{{/each}}``) share the placeholder syntax
    but are not variables: they are never filled, never smart-filled, and must
    not be reported to callers that validate a field map against the body.
    """

    variables: list[str] = []
    seen: set[str] = set()
    for match in VARIABLE_PATTERN.finditer(template_body):
        variable = match.group(1).strip()
        if variable.startswith(("#", "/")):
            continue
        if variable and variable not in seen:
            variables.append(variable)
            seen.add(variable)
    return variables


def extract_schema_variables(template: Any) -> list[str]:
    schema = getattr(template, "variable_schema", None) or {}
    fields = schema.get("fields") if isinstance(schema, dict) else None
    variables: list[str] = []
    seen: set[str] = set()
    if not isinstance(fields, list):
        return variables
    for entry in fields:
        if not isinstance(entry, dict):
            continue
        variable = entry.get("name") or entry.get("variable") or entry.get("key")
        if not variable:
            continue
        variable = str(variable).strip()
        if variable and variable not in seen:
            variables.append(variable)
            seen.add(variable)
    return variables


def template_variables(template: Any) -> list[str]:
    """Body placeholders first, then schema fields, each name once."""

    variables: list[str] = []
    for variable in [
        *extract_template_variables(getattr(template, "body", "") or ""),
        *extract_schema_variables(template),
    ]:
        if variable not in variables:
            variables.append(variable)
    return variables


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------


def stringify_suggestion(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class Collision:
    """Two sources wrote one alias. The first write is the one a fill sees."""

    alias: str
    winner: dict[str, Any]
    losers: tuple[dict[str, Any], ...]

    @property
    def same_value(self) -> bool:
        return all(loser["value"] == self.winner["value"] for loser in self.losers)


class CandidateIndex(dict):
    """``{alias: suggestion}`` with a record of every write that reached it.

    It is a ``dict`` so every caller of the old candidate map keeps working.
    ``add`` keeps first-writer-wins semantics -- the contract every parity test
    pins -- and ``collisions`` reports the aliases where that choice mattered.
    """

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[dict[str, Any]] = []

    def add(
        self,
        alias: str,
        value: Any,
        *,
        source_type: str,
        source_field: str,
        record_id: uuid.UUID | str | None = None,
        confidence: float = 1.0,
        review_required: bool = False,
        provenance: dict[str, Any] | None = None,
    ) -> bool:
        suggested_value = stringify_suggestion(value)
        if suggested_value is None:
            return False
        key = normalize_variable_name(alias)
        self.writes.append(
            {
                "alias": key,
                "source_type": source_type,
                "source_field": source_field,
                "value": suggested_value,
            }
        )
        if key in self:
            return False
        candidate_provenance = {
            "source_type": source_type,
            "source_field": source_field,
            "record_id": str(record_id) if record_id else None,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        if provenance:
            candidate_provenance.update(provenance)
        self[key] = DocumentTemplateVariableSuggestion(
            variable=alias,
            suggested_value=suggested_value,
            source_type=source_type,
            source_field=source_field,
            provenance=candidate_provenance,
            confidence=confidence,
            review_required=review_required,
        )
        return True

    def collisions(self, *, include_agreeing: bool = False) -> list[Collision]:
        by_alias: dict[str, list[dict[str, Any]]] = {}
        for write in self.writes:
            by_alias.setdefault(write["alias"], []).append(write)
        output: list[Collision] = []
        for alias, entries in by_alias.items():
            if len(entries) < 2:
                continue
            collision = Collision(alias, entries[0], tuple(entries[1:]))
            if collision.same_value and not include_agreeing:
                continue
            output.append(collision)
        return output


def add_candidate(
    candidates: dict[str, DocumentTemplateVariableSuggestion],
    alias: str,
    value: Any,
    *,
    source_type: str,
    source_field: str,
    record_id: uuid.UUID | str | None = None,
    confidence: float = 1.0,
    review_required: bool = False,
    provenance: dict[str, Any] | None = None,
) -> None:
    """Write one candidate with first-writer-wins semantics.

    Accepts a plain dict as well as a :class:`CandidateIndex` so the sources
    can be exercised against either.
    """

    if isinstance(candidates, CandidateIndex):
        candidates.add(
            alias,
            value,
            source_type=source_type,
            source_field=source_field,
            record_id=record_id,
            confidence=confidence,
            review_required=review_required,
            provenance=provenance,
        )
        return
    suggested_value = stringify_suggestion(value)
    if suggested_value is None:
        return
    key = normalize_variable_name(alias)
    candidate_provenance = {
        "source_type": source_type,
        "source_field": source_field,
        "record_id": str(record_id) if record_id else None,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    if provenance:
        candidate_provenance.update(provenance)
    candidates.setdefault(
        key,
        DocumentTemplateVariableSuggestion(
            variable=alias,
            suggested_value=suggested_value,
            source_type=source_type,
            source_field=source_field,
            provenance=candidate_provenance,
            confidence=confidence,
            review_required=review_required,
        ),
    )


def mapping_value(mapping: dict | None, key: str) -> str | None:
    """Read one key out of a JSON contact column (address, emergency contact)."""

    if not isinstance(mapping, dict):
        return None
    return stringify_suggestion(mapping.get(key))


# --------------------------------------------------------------------------
# Records the sources read
# --------------------------------------------------------------------------


@dataclass
class FillRecords:
    """Everything a fill can draw from, loaded or supplied in memory."""

    matter: Any = None
    parties: Sequence[Any] = ()
    current_user: Any = None
    retainer: Any = None
    estate: Any = None


@dataclass(frozen=True)
class FillNeeds:
    """What one template asks for, in alias terms, before anything is loaded."""

    binding_aliases: frozenset[str]
    name_keys: frozenset[str]

    @classmethod
    def of(cls, bindings: dict[str, str], variables: Iterable[str]) -> "FillNeeds":
        aliases = set()
        for binding in bindings.values():
            alias = template_cards.alias_for_path(binding)
            if alias:
                aliases.add(normalize_variable_name(alias))
        return cls(
            binding_aliases=frozenset(aliases),
            name_keys=frozenset(normalize_variable_name(v) for v in variables),
        )

    def any_of(self, aliases: frozenset[str]) -> bool:
        return bool(aliases & (self.binding_aliases | self.name_keys))


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


class FillSource:
    """One record family the fill can draw from.

    ``aliases`` is the static declaration of what :meth:`collect` can write.
    It feeds :func:`vocabulary` and :meth:`needed`, so a source that writes an
    alias it did not declare fails the vocabulary parity test rather than
    silently escaping the approval gate.
    """

    key: str = ""
    #: Loaded for every matter, regardless of the template.
    always: bool = True

    @property
    def aliases(self) -> frozenset[str]:  # pragma: no cover - overridden
        raise NotImplementedError

    def needed(self, needs: FillNeeds) -> bool:
        return self.always or needs.any_of(self.aliases)

    def collect(
        self, index: CandidateIndex, records: FillRecords
    ) -> None:  # pragma: no cover
        raise NotImplementedError


class CurrentUserSource(FillSource):
    key = "current_user"

    @property
    def aliases(self) -> frozenset[str]:
        return frozenset({"current_user_name", "current_user_email", "prepared_by"})

    def collect(self, index: CandidateIndex, records: FillRecords) -> None:
        current_user = records.current_user
        add_candidate(
            index,
            "current_user_name",
            getattr(current_user, "full_name", None),
            source_type="current_user",
            source_field="full_name",
            record_id=getattr(current_user, "id", None),
        )
        add_candidate(
            index,
            "current_user_email",
            getattr(current_user, "email", None),
            source_type="current_user",
            source_field="email",
            record_id=getattr(current_user, "id", None),
        )
        add_candidate(
            index,
            "prepared_by",
            getattr(current_user, "full_name", None)
            or getattr(current_user, "email", None),
            source_type="current_user",
            source_field="full_name",
            record_id=getattr(current_user, "id", None),
        )


class EstateSource(FillSource):
    """The estate linked to the matter, composed by ``probate.bindings``."""

    key = "estate"
    always = False

    @property
    def aliases(self) -> frozenset[str]:
        return _estate_aliases()

    def collect(self, index: CandidateIndex, records: FillRecords) -> None:
        for alias, value, source_field, record_id in probate_bindings.estate_candidates(
            records.estate
        ):
            add_candidate(
                index,
                alias,
                value,
                source_type="estate",
                source_field=source_field,
                record_id=record_id,
            )


@functools.lru_cache(maxsize=1)
def _estate_aliases() -> frozenset[str]:
    return frozenset(
        normalize_variable_name(alias)
        for alias in probate_bindings.estate_values(probate_bindings.probe_estate())
    )


#: ``alias -> matter attribute`` for the columns the matter supplies directly.
MATTER_FIELDS: tuple[tuple[str, str], ...] = (
    ("matter_id", "id"),
    ("matter_name", "matter_name"),
    ("matter_type", "matter_type"),
    ("matter_description", "description"),
    ("matter_status", "status"),
    ("matter_stage", "stage"),
    ("matter_jurisdiction", "jurisdiction"),
    ("jurisdiction", "jurisdiction"),
    ("case_number", "case_number"),
    ("court", "court"),
    ("judge", "judge"),
    ("billing_method", "billing_method"),
    ("billing_cycle", "billing_cycle"),
    ("hourly_rate", "hourly_rate"),
    ("budget_amount", "budget_amount"),
    ("contingency_percentage", "contingency_percentage"),
    ("venue", "venue"),
    ("matter_role", "role"),
    ("represented_side", "role"),
    ("counterparty", "counterparty"),
    # Reachable since the engine: the human-facing number, the practice the
    # firm files the matter under, and the day it opened.
    ("matter_number", "matter_number"),
    ("practice_area", "practice_area"),
    ("opened_on", "opened_on"),
)


class MatterSource(FillSource):
    key = "matter"

    @property
    def aliases(self) -> frozenset[str]:
        return frozenset(alias for alias, _ in MATTER_FIELDS)

    def collect(self, index: CandidateIndex, records: FillRecords) -> None:
        matter = records.matter
        for alias, attribute in MATTER_FIELDS:
            # getattr: fixtures and pre-venue matters may not carry the attribute.
            add_candidate(
                index,
                alias,
                getattr(matter, attribute, None),
                source_type="matter",
                source_field=alias,
                record_id=matter.id,
            )


class RetainerSource(FillSource):
    key = "retainer"
    always = False

    @property
    def aliases(self) -> frozenset[str]:
        return frozenset({"retainer_amount", "retainer_minimum_balance"})

    def collect(self, index: CandidateIndex, records: FillRecords) -> None:
        retainer = records.retainer
        if retainer is None:
            return
        add_candidate(
            index,
            "retainer_amount",
            retainer.amount,
            source_type="retainer",
            source_field="amount",
            record_id=retainer.id,
        )
        add_candidate(
            index,
            "retainer_minimum_balance",
            retainer.minimum_balance,
            source_type="retainer",
            source_field="minimum_balance",
            record_id=retainer.id,
        )


#: The two roles ``matter.role`` can stand in for when no party rows exist.
CAPTION_ROLES: tuple[str, ...] = ("plaintiff", "defendant")
#: Every party role that gets its own aliases. ``client`` is left out because
#: the client contact already owns ``client_*`` and a party row would shadow
#: it; ``other`` names nothing a template could sensibly ask for.
PARTY_ROLES: tuple[str, ...] = (
    "plaintiff",
    "defendant",
    "petitioner",
    "respondent",
    "opposing_party",
    "counsel",
    "witness",
    "expert",
)
_ADDRESS_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("street", "street"),
    ("city", "city"),
    ("state", "state"),
    ("zip", "zip"),
    ("country", "country"),
)


def caption_parties(parties: Sequence[Any], role: str) -> list[Any]:
    matching: list[Any] = []
    for party in parties:
        try:
            party_role = normalize_matter_party_role(getattr(party, "role", "other"))
        except ValueError:
            continue
        if party_role != role:
            continue
        if not stringify_suggestion(
            getattr(getattr(party, "contact", None), "display_name", None)
        ):
            continue
        matching.append(party)
    return sorted(
        matching,
        key=lambda party: (
            not bool(getattr(party, "is_primary", False)),
            str(getattr(party, "created_at", "")),
            str(getattr(party, "id", "")),
        ),
    )


def role_aliases(role: str) -> frozenset[str]:
    """Every alias the caption builder writes for one role's first instance."""

    return frozenset(
        {
            role,
            f"{role}_name",
            f"{role}s",
            f"{role}_names",
            f"{role}_email",
            f"{role}_phone",
        }
        | {f"{role}_{suffix}" for suffix, _ in _ADDRESS_SUFFIXES}
    )


def role_instance_aliases(role: str) -> frozenset[str]:
    """Aliases for instances 2..N of a role card, e.g. ``defendant_2_name``.

    These are producible but were never part of the approval vocabulary: the
    probe that used to compute it carried one party per role. They stay out
    of :func:`vocabulary` so the gate's answer does not change here.
    """

    card = template_cards.card(role)
    if card is None or card.kind is not CardKind.ROLE:
        return frozenset()
    aliases = set()
    for index in range(2, card.max_instances + 1):
        for name in ("full_name", "email", "phone"):
            entry = card.field(name)
            if entry is not None:
                aliases.add(
                    normalize_variable_name(
                        template_cards.indexed_alias(role, index, entry)
                    )
                )
    return frozenset(aliases)


def _add_role_instance_candidates(
    index: CandidateIndex, role: str, role_parties: Sequence[Any]
) -> None:
    """Emit an alias per addressable instance of a role card.

    A caption with two defendants could previously only name the first one; the
    second existed on the matter and was unreachable from a template.  Instance
    order is the order the party loader already establishes -- primary first,
    then ``created_at``, then id -- so the same template fills the same way on
    two different days.

    Instance 1 is deliberately skipped: it already resolves through the
    singular alias, and emitting a second key for the same record would let two
    spellings of one field drift apart.
    """

    card = template_cards.card(role)
    if card is None or card.kind is not CardKind.ROLE:
        return
    for position, party in enumerate(role_parties[: card.max_instances], start=1):
        if position == 1:
            continue
        contact = party.contact
        if contact is None:
            continue
        provenance = {
            "party_role": role,
            "selection": f"instance_{position}",
            "contact_id": str(contact.id),
        }
        for entry, value, source_field in (
            (card.field("full_name"), contact.display_name, "contact.display_name"),
            (card.field("email"), contact.email, "contact.email"),
            (card.field("phone"), contact.phone, "contact.phone"),
        ):
            if entry is None:
                continue
            add_candidate(
                index,
                template_cards.indexed_alias(role, position, entry),
                value,
                source_type="matter_party",
                source_field=source_field,
                record_id=party.id,
                provenance=provenance,
            )


class CaptionPartySource(FillSource):
    """Structured party rows, one alias family per role."""

    key = "matter_party"

    @property
    def aliases(self) -> frozenset[str]:
        return frozenset().union(*(role_aliases(role) for role in PARTY_ROLES))

    @property
    def instance_aliases(self) -> frozenset[str]:
        return frozenset().union(*(role_instance_aliases(role) for role in PARTY_ROLES))

    def collect(self, index: CandidateIndex, records: FillRecords) -> None:
        for role in PARTY_ROLES:
            role_parties = caption_parties(records.parties, role)
            if not role_parties:
                continue

            primary_party = role_parties[0]
            primary_contact = primary_party.contact
            primary_name = primary_contact.display_name
            selection = (
                "primary"
                if bool(getattr(primary_party, "is_primary", False))
                else "first_listed"
            )
            singular_provenance = {
                "party_role": role,
                "selection": selection,
                "contact_id": str(primary_contact.id),
            }
            for alias in (role, f"{role}_name"):
                add_candidate(
                    index,
                    alias,
                    primary_name,
                    source_type="matter_party",
                    source_field="contact.display_name",
                    record_id=primary_party.id,
                    provenance=singular_provenance,
                )

            unique_names = list(
                dict.fromkeys(party.contact.display_name for party in role_parties)
            )
            all_party_ids = [str(party.id) for party in role_parties]
            for alias in (f"{role}s", f"{role}_names"):
                add_candidate(
                    index,
                    alias,
                    "; ".join(unique_names),
                    source_type="matter_parties",
                    source_field="contacts.display_name",
                    provenance={
                        "party_role": role,
                        "selection": "all",
                        "record_ids": all_party_ids,
                    },
                )

            for suffix, value, source_field in (
                ("email", primary_contact.email, "contact.email"),
                ("phone", primary_contact.phone, "contact.phone"),
            ):
                add_candidate(
                    index,
                    f"{role}_{suffix}",
                    value,
                    source_type="matter_party",
                    source_field=source_field,
                    record_id=primary_party.id,
                    provenance=singular_provenance,
                )
            for suffix, address_key in _ADDRESS_SUFFIXES:
                add_candidate(
                    index,
                    f"{role}_{suffix}",
                    mapping_value(primary_contact.address, address_key),
                    source_type="matter_party",
                    source_field=f"contact.address.{address_key}",
                    record_id=primary_party.id,
                    provenance=singular_provenance,
                )

            _add_role_instance_candidates(index, role, role_parties)


_CLIENT_COLUMNS: tuple[tuple[str, str], ...] = (
    # The parts behind ``display_name``, and the identity columns.
    ("client_first_name", "first_name"),
    ("client_last_name", "last_name"),
    ("client_preferred_name", "preferred_name"),
    ("client_organization_name", "organization_name"),
    ("client_entity_type", "entity_type"),
    ("client_number", "client_number"),
    ("client_date_of_birth", "date_of_birth"),
    ("client_secondary_phone", "secondary_phone"),
    ("client_preferred_contact_method", "preferred_contact_method"),
    ("client_preferred_contact_window", "preferred_contact_window"),
    ("client_preferred_language", "preferred_language"),
    ("client_referral_source", "referral_source"),
)
_EMERGENCY_KEYS: tuple[tuple[str, str], ...] = (
    ("emergency_contact_name", "name"),
    ("emergency_contact_relationship", "relationship"),
    ("emergency_contact_phone", "phone"),
    ("emergency_contact_email", "email"),
)


class ClientContactSource(FillSource):
    key = "contact"

    @property
    def aliases(self) -> frozenset[str]:
        return frozenset(
            {"client_name", "client_email", "client_phone"}
            | {f"client_{suffix}" for suffix, _ in _ADDRESS_SUFFIXES}
            | {alias for alias, _ in _CLIENT_COLUMNS}
            | {alias for alias, _ in _EMERGENCY_KEYS}
        )

    def collect(self, index: CandidateIndex, records: FillRecords) -> None:
        client = getattr(records.matter, "client", None)
        if not client:
            return
        add_candidate(
            index,
            "client_name",
            client.display_name,
            source_type="contact",
            source_field="display_name",
            record_id=client.id,
        )
        add_candidate(
            index,
            "client_email",
            client.email,
            source_type="contact",
            source_field="email",
            record_id=client.id,
        )
        add_candidate(
            index,
            "client_phone",
            client.phone,
            source_type="contact",
            source_field="phone",
            record_id=client.id,
        )
        address = client.address
        for suffix, key in _ADDRESS_SUFFIXES:
            add_candidate(
                index,
                f"client_{suffix}",
                mapping_value(address, key),
                source_type="contact",
                source_field=f"address.{key}",
                record_id=client.id,
            )
        for alias, column in _CLIENT_COLUMNS:
            add_candidate(
                index,
                alias,
                getattr(client, column, None),
                source_type="contact",
                source_field=column,
                record_id=client.id,
            )
        emergency = getattr(client, "emergency_contact", None)
        for alias, key in _EMERGENCY_KEYS:
            add_candidate(
                index,
                alias,
                mapping_value(emergency, key),
                source_type="contact",
                source_field=f"emergency_contact.{key}",
                record_id=client.id,
            )


def represented_caption_role(value: Any) -> str | None:
    tokens = set(normalize_variable_name(str(value or "")).split("_"))
    roles = tokens.intersection(set(CAPTION_ROLES))
    return roles.pop() if len(roles) == 1 else None


class InferredCaptionSource(FillSource):
    """Caption names guessed from ``matter.role`` when no party rows exist.

    The client stands in for the represented side and ``matter.counterparty``
    for the other, at reduced confidence and flagged for review. Structured
    party rows always win because they are collected first.
    """

    key = "inferred_caption"

    @property
    def aliases(self) -> frozenset[str]:
        return frozenset(
            {
                alias
                for role in CAPTION_ROLES
                for alias in (role, f"{role}_name", f"{role}s", f"{role}_names")
            }
        )

    def collect(self, index: CandidateIndex, records: FillRecords) -> None:
        matter = records.matter
        represented_role = represented_caption_role(getattr(matter, "role", None))
        if not represented_role:
            return
        opposing_role = "defendant" if represented_role == "plaintiff" else "plaintiff"
        client = getattr(matter, "client", None)
        if client:
            self._add(
                index,
                role=represented_role,
                value=client.display_name,
                source_type="contact",
                source_field="display_name",
                record_id=client.id,
            )
        self._add(
            index,
            role=opposing_role,
            value=getattr(matter, "counterparty", None),
            source_type="matter",
            source_field="counterparty",
            record_id=matter.id,
        )

    @staticmethod
    def _add(index, *, role, value, source_type, source_field, record_id) -> None:
        for alias in (role, f"{role}_name", f"{role}s", f"{role}_names"):
            add_candidate(
                index,
                alias,
                value,
                source_type=source_type,
                source_field=source_field,
                record_id=record_id,
                confidence=0.75,
                review_required=True,
                provenance={
                    "party_role": role,
                    "selection": "legacy_matter_role_inference",
                },
            )


class AttorneyOfRecordSource(FillSource):
    key = "attorney"

    @property
    def aliases(self) -> frozenset[str]:
        return frozenset({"attorney_name", "attorney_email"})

    def collect(self, index: CandidateIndex, records: FillRecords) -> None:
        attorney = getattr(records.matter, "attorney_of_record", None)
        if not attorney:
            return
        add_candidate(
            index,
            "attorney_name",
            attorney.full_name,
            source_type="user",
            source_field="full_name",
            record_id=attorney.id,
        )
        add_candidate(
            index,
            "attorney_email",
            attorney.email,
            source_type="user",
            source_field="email",
            record_id=attorney.id,
        )


#: The registry, in write order. The first source to write an alias wins.
SOURCES: tuple[FillSource, ...] = (
    CurrentUserSource(),
    EstateSource(),
    MatterSource(),
    RetainerSource(),
    CaptionPartySource(),
    ClientContactSource(),
    InferredCaptionSource(),
    AttorneyOfRecordSource(),
)

#: Sources that need no matter at all.
_MATTERLESS_KEYS = frozenset({"current_user"})


def source(key: str) -> FillSource:
    for entry in SOURCES:
        if entry.key == key:
            return entry
    raise KeyError(key)


#: Field names a person types that mean one of the client's aliases. Applied
#: only on the name-match branch -- a binding is never second-guessed -- and
#: reported in provenance, at reduced confidence, because "first name" on a
#: caption form may not be the client's.
NAME_SYNONYMS: dict[str, str] = {
    "first_name": "client_first_name",
    "last_name": "client_last_name",
    "full_name": "client_name",
    "name": "client_name",
    "email": "client_email",
    "email_address": "client_email",
    "phone": "client_phone",
    "phone_number": "client_phone",
    "telephone": "client_phone",
    "street": "client_street",
    "street_address": "client_street",
    "address": "client_street",
    "city": "client_city",
    "state": "client_state",
    "zip": "client_zip",
    "zip_code": "client_zip",
    "postal_code": "client_zip",
    "date_of_birth": "client_date_of_birth",
    "dob": "client_date_of_birth",
    "organization": "client_organization_name",
    "company": "client_organization_name",
    "company_name": "client_organization_name",
}


@functools.lru_cache(maxsize=1)
def vocabulary() -> frozenset[str]:
    """Every field name Smart Fill can fill without a binding.

    The union of what the sources declare, plus the synonyms the name-match
    branch understands. ``tests/test_template_fill_engine`` asserts the source
    part equals what the resolver actually writes against a fully populated
    probe, so a source cannot declare an alias it never produces or produce
    one it never declared.
    """

    return source_vocabulary() | frozenset(NAME_SYNONYMS)


@functools.lru_cache(maxsize=1)
def source_vocabulary() -> frozenset[str]:
    """The aliases the sources write, before synonyms."""

    return frozenset().union(*(entry.aliases for entry in SOURCES))


def collect(records: FillRecords) -> CandidateIndex:
    """Run every source over ``records`` in registry order."""

    index = CandidateIndex()
    for entry in SOURCES:
        if records.matter is None and entry.key not in _MATTERLESS_KEYS:
            continue
        entry.collect(index, records)
    return index


def collect_candidates(
    *,
    matter: Any,
    parties: Sequence[Any] = (),
    current_user: Any,
    retainer: Any = None,
    estate: Any = None,
) -> CandidateIndex:
    """The old ``_collect_smart_fill_candidates`` signature, unchanged."""

    return collect(
        FillRecords(
            matter=matter,
            parties=parties,
            current_user=current_user,
            retainer=retainer,
            estate=estate,
        )
    )


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def bound_suggestion(
    variable: str,
    binding: str,
    candidates: dict[str, DocumentTemplateVariableSuggestion],
) -> DocumentTemplateVariableSuggestion:
    """Resolve one field through its declared binding.

    An unresolved binding is reported with the path that failed, so the user
    can see the field is bound to a record the current matter does not carry
    rather than a blank box with no explanation.
    """

    if binding == MANUAL_BINDING:
        return DocumentTemplateVariableSuggestion(
            variable=variable,
            provenance={"status": "manual_entry", "binding": binding},
            review_required=True,
        )
    if is_item_binding(binding):
        # Its value comes from whichever item of a repeating section is being
        # rendered, so there is nothing for a person to fill in once.
        return DocumentTemplateVariableSuggestion(
            variable=variable,
            provenance={
                "status": "repeat_item",
                "binding": binding,
                "binding_label": template_cards.label_for_path(binding),
            },
            review_required=False,
        )
    alias = template_cards.alias_for_path(binding)
    candidate = candidates.get(alias) if alias else None
    if candidate is not None:
        provenance = {
            **candidate.provenance,
            "binding": binding,
            "binding_label": template_cards.label_for_path(binding),
        }
        return candidate.model_copy(
            update={"variable": variable, "provenance": provenance}
        )
    return DocumentTemplateVariableSuggestion(
        variable=variable,
        provenance={
            # A path the catalogue no longer describes has no label; saying so
            # is more useful than omitting the key.
            "status": "binding_unresolved",
            "binding": binding,
            "binding_label": template_cards.label_for_path(binding)
            or "Unknown data source",
        },
        review_required=True,
    )


def resolve_variables(
    variables: Iterable[str],
    *,
    bindings: dict[str, str],
    candidates: dict[str, DocumentTemplateVariableSuggestion],
    firm: dict[str, DocumentTemplateVariableSuggestion],
    custom: dict[str, DocumentTemplateVariableSuggestion],
) -> list[DocumentTemplateVariableSuggestion]:
    """Firm profile > custom field > declared binding > name match > nothing."""

    suggestions: list[DocumentTemplateVariableSuggestion] = []
    for variable in variables:
        if variable in firm:
            suggestions.append(firm[variable])
            continue
        if variable in custom:
            suggestions.append(custom[variable])
            continue
        binding = bindings.get(variable)
        if binding:
            # A declared binding is authoritative. Falling back to name
            # matching here would reintroduce exactly the surprise bindings
            # exist to remove: a field the customer bound to one record
            # silently filling from another because of its name.
            suggestions.append(bound_suggestion(variable, binding, candidates))
            continue
        key = normalize_variable_name(variable)
        candidate = candidates.get(key)
        if candidate:
            suggestions.append(candidate.model_copy(update={"variable": variable}))
            continue
        synonym = NAME_SYNONYMS.get(key)
        candidate = candidates.get(synonym) if synonym else None
        if candidate:
            suggestions.append(
                candidate.model_copy(
                    update={
                        "variable": variable,
                        "confidence": min(candidate.confidence, 0.9),
                        "review_required": True,
                        "provenance": {**candidate.provenance, "synonym_of": synonym},
                    }
                )
            )
            continue
        suggestions.append(
            DocumentTemplateVariableSuggestion(
                variable=variable,
                provenance={"status": "no_deterministic_source"},
                review_required=True,
            )
        )
    return suggestions


@dataclass
class PreparedFill:
    """The result of filling one template from one matter.

    ``suggestions`` is what the preview route returns. ``values`` is the same
    thing shaped for a renderer: every non-empty suggestion for an included,
    non-signing field. ``coverage`` is the schema's fill split and
    ``missing_required`` the included required fields that still have no
    value -- what a person must supply before this document can be generated.
    """

    matter_id: str | None
    suggestions: list[DocumentTemplateVariableSuggestion]
    values: dict[str, str]
    coverage: FillCoverage
    missing_required: list[str]
    collisions: list[Collision] = field(default_factory=list)
    sources_loaded: tuple[str, ...] = ()

    @property
    def by_variable(self) -> dict[str, DocumentTemplateVariableSuggestion]:
        return {item.variable: item for item in self.suggestions}


def _schema_fields(template: Any) -> list[dict[str, Any]]:
    schema = getattr(template, "variable_schema", None)
    fields = schema.get("fields") if isinstance(schema, dict) else None
    return [entry for entry in fields or [] if isinstance(entry, dict)]


def render_values(
    template: Any, suggestions: Iterable[DocumentTemplateVariableSuggestion]
) -> tuple[dict[str, str], list[str]]:
    """``(values, missing_required)`` for a renderer, from the suggestions."""

    by_variable = {item.variable: item for item in suggestions}
    fields_by_name = {
        str(entry.get("name") or "").strip(): entry
        for entry in _schema_fields(template)
    }
    values: dict[str, str] = {}
    missing_required: list[str] = []
    for variable, suggestion in by_variable.items():
        spec = fields_by_name.get(variable, {})
        if spec.get("included", True) is False:
            continue
        if spec and is_signing_field(spec):
            continue
        value = suggestion.suggested_value
        if value not in (None, ""):
            values[variable] = str(value)
        elif spec.get("required"):
            missing_required.append(variable)
    return values, missing_required


async def prepare_fill(
    db: Any,
    *,
    template: Any,
    tenant_id: uuid.UUID,
    matter: Any = None,
    matter_id: str | None = None,
    actor: Any = None,
    requested_variables: list[str] | None = None,
    loaders: Loaders = DEFAULT_LOADERS,
) -> PreparedFill:
    """Fill ``template`` from a matter, loading only the records it needs.

    ``matter`` may be passed directly (a job that already holds the row) or
    named by ``matter_id`` and loaded. ``actor`` is whoever the fill is for;
    it supplies the ``prepared_by`` family and may be ``None``.
    """

    if matter is None and matter_id:
        matter = await loaders.matter(db=db, tenant_id=tenant_id, matter_id=matter_id)
    parties = await loaders.parties(db=db, tenant_id=tenant_id, matter=matter)
    variables = (
        requested_variables
        if requested_variables is not None
        else template_variables(template)
    )
    bindings = declared_bindings(getattr(template, "variable_schema", None))
    needs = FillNeeds.of(bindings, variables)

    loaded: list[str] = []
    retainer = None
    estate = None
    if matter is not None:
        loaded.extend(("matter", "matter_party"))
        # The retainer and estate are extra queries, so they are read only
        # when this template can actually fill from them: a declared binding
        # or an unbound field named after one of their aliases.
        if source("retainer").needed(needs):
            retainer = await loaders.retainer(db=db, tenant_id=tenant_id, matter=matter)
            loaded.append("retainer")
        if source("estate").needed(needs):
            estate = await loaders.estate(db=db, tenant_id=tenant_id, matter=matter)
            loaded.append("estate")

    index = collect(
        FillRecords(
            matter=matter,
            parties=parties,
            current_user=actor,
            retainer=retainer,
            estate=estate,
        )
    )
    custom = await template_custom_fields.suggestions(db, tenant_id, matter, bindings)
    firm = await template_firm_fields.suggestions(db, tenant_id, bindings)
    suggestions = resolve_variables(
        variables, bindings=bindings, candidates=index, firm=firm, custom=custom
    )
    fields_by_name = {
        str(entry.get("name") or "").strip(): entry
        for entry in _schema_fields(template)
    }
    suggestions = [
        template_fill_formatters.format_suggestion(
            item, fields_by_name.get(item.variable)
        )
        for item in suggestions
    ]
    values, missing_required = render_values(template, suggestions)
    return PreparedFill(
        matter_id=str(matter.id) if matter is not None else None,
        suggestions=suggestions,
        values=values,
        coverage=fill_coverage(
            getattr(template, "variable_schema", None), vocabulary=vocabulary()
        ),
        missing_required=missing_required,
        collisions=index.collisions(),
        sources_loaded=tuple(loaded),
    )


__all__ = [
    "VARIABLE_PATTERN",
    "CandidateIndex",
    "Collision",
    "FillNeeds",
    "FillRecords",
    "FillSource",
    "NAME_SYNONYMS",
    "PARTY_ROLES",
    "PreparedFill",
    "SOURCES",
    "add_candidate",
    "bound_suggestion",
    "caption_parties",
    "collect",
    "collect_candidates",
    "extract_schema_variables",
    "extract_template_variables",
    "mapping_value",
    "prepare_fill",
    "render_values",
    "represented_caption_role",
    "resolve_variables",
    "role_aliases",
    "role_instance_aliases",
    "source",
    "source_vocabulary",
    "stringify_suggestion",
    "template_variables",
    "vocabulary",
]
