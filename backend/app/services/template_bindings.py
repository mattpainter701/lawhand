"""Template field data bindings.

A binding says where a template field's value comes from: one path out of a
closed, server-owned catalogue of matter, client, party, and user records.

Before bindings, Smart Fill matched a fixed alias dictionary against the *field
name*, so it only ever fired when a customer happened to name a field the way
the server hardcoded it.  A firm's own engagement letter with a
``client_full_name`` field resolved to nothing.  A binding moves that knowledge
into the template, where the customer states it once and it holds for the life
of the template.

The catalogue is deliberately closed.  A binding is a lookup key, never an
expression, so nothing a customer authors can reach a renderer or a query.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

#: A field the customer always types by hand.  Declaring it suppresses the
#: legacy name-matching fallback, so an intentionally manual field stops being
#: silently auto-filled by a coincidental name collision.
MANUAL_BINDING = "manual"


@dataclass(frozen=True)
class TemplateBinding:
    """One catalogue entry.

    ``alias`` is the key the existing Smart Fill candidate builder already
    resolves.  Keeping the binding path separate from the alias lets the
    catalogue present a stable, self-describing vocabulary to customers while
    the resolver keeps using the reviewed candidate map underneath.
    """

    path: str
    alias: str
    label: str
    group: str


_CATALOGUE: tuple[TemplateBinding, ...] = (
    # Shared within the current firm, independent of the selected matter.
    TemplateBinding("firm.name", "firm_name", "Firm name", "Firm profile"),
    TemplateBinding("firm.address", "firm_address", "Firm address", "Firm profile"),
    TemplateBinding("firm.phone", "firm_phone", "Firm phone", "Firm profile"),
    TemplateBinding("firm.email", "firm_email", "Firm email", "Firm profile"),
    TemplateBinding("firm.website", "firm_website", "Firm website", "Firm profile"),
    # Matter
    TemplateBinding("matter.name", "matter_name", "Matter name", "Matter"),
    TemplateBinding("matter.type", "matter_type", "Matter type", "Matter"),
    TemplateBinding(
        "matter.description", "matter_description", "Matter description", "Matter"
    ),
    TemplateBinding("matter.status", "matter_status", "Matter status", "Matter"),
    TemplateBinding("matter.stage", "matter_stage", "Matter stage", "Matter"),
    TemplateBinding(
        "matter.jurisdiction", "matter_jurisdiction", "Jurisdiction", "Matter"
    ),
    TemplateBinding("matter.venue", "venue", "Venue", "Matter"),
    TemplateBinding("matter.case_number", "case_number", "Case number", "Matter"),
    TemplateBinding("matter.court", "court", "Court", "Matter"),
    TemplateBinding("matter.judge", "judge", "Judge", "Matter"),
    TemplateBinding("matter.counterparty", "counterparty", "Counterparty", "Matter"),
    TemplateBinding("matter.role", "matter_role", "Represented side", "Matter"),
    # Billing
    TemplateBinding(
        "matter.billing_method", "billing_method", "Billing method", "Billing"
    ),
    TemplateBinding(
        "matter.billing_cycle", "billing_cycle", "Billing cycle", "Billing"
    ),
    TemplateBinding("matter.hourly_rate", "hourly_rate", "Hourly rate", "Billing"),
    TemplateBinding(
        "matter.budget_amount", "budget_amount", "Budget amount", "Billing"
    ),
    # The retainer bindings resolve from the matter's *current* retainer record:
    # the most recently created active retainer (falling back to the most
    # recent of any status), never a sum across the matter's retainer history.
    TemplateBinding(
        "matter.contingency_percentage",
        "contingency_percentage",
        "Contingency percentage",
        "Billing",
    ),
    TemplateBinding(
        "matter.retainer_amount", "retainer_amount", "Retainer amount", "Billing"
    ),
    TemplateBinding(
        "matter.retainer_minimum_balance",
        "retainer_minimum_balance",
        "Retainer minimum balance",
        "Billing",
    ),
    # Client contact
    TemplateBinding("client.name", "client_name", "Client name", "Client"),
    TemplateBinding("client.email", "client_email", "Client email", "Client"),
    TemplateBinding("client.phone", "client_phone", "Client phone", "Client"),
    TemplateBinding(
        "client.address.street", "client_street", "Client street", "Client"
    ),
    TemplateBinding("client.address.city", "client_city", "Client city", "Client"),
    TemplateBinding("client.address.state", "client_state", "Client state", "Client"),
    TemplateBinding("client.address.zip", "client_zip", "Client ZIP", "Client"),
    TemplateBinding(
        "client.address.country", "client_country", "Client country", "Client"
    ),
    # Columns the contact record already carries. A firm's own intake form asks
    # for these, and before they were listed here the only way to fill one was
    # to retype an answer the client had already given.
    TemplateBinding(
        "client.date_of_birth",
        "client_date_of_birth",
        "Client date of birth",
        "Client",
    ),
    TemplateBinding(
        "client.secondary_phone",
        "client_secondary_phone",
        "Client secondary phone",
        "Client",
    ),
    TemplateBinding(
        "client.preferred_contact_method",
        "client_preferred_contact_method",
        "Preferred contact method",
        "Client",
    ),
    TemplateBinding(
        "client.preferred_contact_window",
        "client_preferred_contact_window",
        "Best time to reach the client",
        "Client",
    ),
    TemplateBinding(
        "client.preferred_language",
        "client_preferred_language",
        "Preferred language",
        "Client",
    ),
    TemplateBinding(
        "client.referral_source",
        "client_referral_source",
        "How the client found the firm",
        "Client",
    ),
    # The emergency contact is one JSON column on the contact; its keys are the
    # EmergencyContact schema in app/schemas/client.py.
    TemplateBinding(
        "client.emergency_contact.name",
        "emergency_contact_name",
        "Emergency contact name",
        "Emergency contact",
    ),
    TemplateBinding(
        "client.emergency_contact.relationship",
        "emergency_contact_relationship",
        "Emergency contact relationship",
        "Emergency contact",
    ),
    TemplateBinding(
        "client.emergency_contact.phone",
        "emergency_contact_phone",
        "Emergency contact phone",
        "Emergency contact",
    ),
    TemplateBinding(
        "client.emergency_contact.email",
        "emergency_contact_email",
        "Emergency contact email",
        "Emergency contact",
    ),
    # Caption parties
    TemplateBinding(
        "party.plaintiff.name", "plaintiff_name", "Plaintiff (first listed)", "Parties"
    ),
    TemplateBinding(
        "party.plaintiff.names", "plaintiff_names", "Plaintiffs (all)", "Parties"
    ),
    TemplateBinding(
        "party.defendant.name", "defendant_name", "Defendant (first listed)", "Parties"
    ),
    TemplateBinding(
        "party.defendant.names", "defendant_names", "Defendants (all)", "Parties"
    ),
    # People
    TemplateBinding("attorney.name", "attorney_name", "Attorney of record", "People"),
    TemplateBinding("attorney.email", "attorney_email", "Attorney email", "People"),
    TemplateBinding("current_user.name", "current_user_name", "Current user", "People"),
    TemplateBinding(
        "current_user.email", "current_user_email", "Current user email", "People"
    ),
    TemplateBinding("current_user.prepared_by", "prepared_by", "Prepared by", "People"),
    # Estate (probate). Resolved from the Estate record linked to the matter —
    # its columns, its fiduciaries and beneficiaries, and the probate facts the
    # intake gathered — so a court form fills from the record the firm already
    # keeps, not from a second copy of the same answers.
    TemplateBinding(
        "estate.decedent_name", "estate_decedent_name", "Decedent name", "Estate"
    ),
    TemplateBinding(
        "estate.decedent_aka", "estate_decedent_aka", "Decedent also known as", "Estate"
    ),
    TemplateBinding(
        "estate.date_of_death", "estate_date_of_death", "Date of death", "Estate"
    ),
    TemplateBinding(
        "estate.age_at_death", "estate_age_at_death", "Age at death", "Estate"
    ),
    TemplateBinding(
        "estate.domicile_state",
        "estate_domicile_state",
        "State of domicile at death",
        "Estate",
    ),
    TemplateBinding(
        "estate.domicile_county",
        "estate_domicile_county",
        "County of domicile at death",
        "Estate",
    ),
    TemplateBinding(
        "estate.venue_county", "estate_venue_county", "Venue county", "Estate"
    ),
    TemplateBinding(
        "estate.venue_basis",
        "estate_venue_basis",
        "Why venue lies in this county",
        "Estate",
    ),
    TemplateBinding("estate.court_name", "estate_court", "Probate court", "Estate"),
    TemplateBinding(
        "estate.case_number", "estate_case_number", "Probate case number", "Estate"
    ),
    TemplateBinding(
        "estate.will_execution_date",
        "estate_will_date",
        "Date the will was signed",
        "Estate",
    ),
    TemplateBinding(
        "estate.gross_value", "estate_gross_value", "Gross estate value", "Estate"
    ),
    TemplateBinding(
        "estate.net_value", "estate_net_value", "Net estate value", "Estate"
    ),
    TemplateBinding(
        "estate.probate_track_label",
        "estate_probate_track",
        "Probate proceeding",
        "Estate",
    ),
    TemplateBinding(
        "estate.heirs_table",
        "estate_heirs_table",
        "Heirs and devisees (name, age, relationship, address)",
        "Estate",
    ),
    TemplateBinding(
        "estate.heir_names",
        "estate_heir_names",
        "Heirs and devisees (names only)",
        "Estate",
    ),
    TemplateBinding(
        "estate.applicant_name",
        "estate_applicant_name",
        "Applicant name",
        "Estate applicant",
    ),
    TemplateBinding(
        "estate.applicant_name_and_interest",
        "estate_applicant_interest",
        "Applicant name and interest in the estate",
        "Estate applicant",
    ),
    TemplateBinding(
        "estate.applicant_address",
        "estate_applicant_address",
        "Applicant street address",
        "Estate applicant",
    ),
    TemplateBinding(
        "estate.applicant_city_state_zip",
        "estate_applicant_city_state_zip",
        "Applicant city, state, ZIP",
        "Estate applicant",
    ),
    TemplateBinding(
        "estate.applicant_full_address",
        "estate_applicant_full_address",
        "Applicant full mailing address",
        "Estate applicant",
    ),
    TemplateBinding(
        "estate.applicant_phone",
        "estate_applicant_phone",
        "Applicant phone",
        "Estate applicant",
    ),
    TemplateBinding(
        "estate.applicant_email",
        "estate_applicant_email",
        "Applicant email",
        "Estate applicant",
    ),
    TemplateBinding(
        "estate.pr_name",
        "estate_pr_name",
        "Personal representative name",
        "Personal representative",
    ),
    TemplateBinding(
        "estate.pr_address",
        "estate_pr_address",
        "Personal representative address",
        "Personal representative",
    ),
    TemplateBinding(
        "estate.pr_phone",
        "estate_pr_phone",
        "Personal representative phone",
        "Personal representative",
    ),
    TemplateBinding(
        "estate.pr_email",
        "estate_pr_email",
        "Personal representative email",
        "Personal representative",
    ),
    TemplateBinding(
        "estate.pr_priority_statement",
        "estate_pr_priority",
        "Priority for appointment",
        "Personal representative",
    ),
    TemplateBinding(
        "estate.pr_prior_priority_persons",
        "estate_pr_prior_persons",
        "Persons with prior or equal priority",
        "Personal representative",
    ),
    TemplateBinding(
        "estate.prior_appointment_statement",
        "estate_prior_appointment",
        "Prior appointment statement",
        "Estate statements",
    ),
    TemplateBinding(
        "estate.demand_for_notice_statement",
        "estate_demand_for_notice",
        "Demand for notice statement",
        "Estate statements",
    ),
    TemplateBinding(
        "estate.unprobated_instrument_statement",
        "estate_unprobated_instrument",
        "Why an instrument is not being probated",
        "Estate statements",
    ),
    TemplateBinding(
        "estate.bond_amount", "estate_bond_amount", "Bond amount", "Estate statements"
    ),
    TemplateBinding(
        "estate.appointment_date",
        "estate_appointment_date",
        "Date of appointment",
        "Estate dates",
    ),
    TemplateBinding(
        "estate.letters_issued_date",
        "estate_letters_date",
        "Date letters were issued",
        "Estate dates",
    ),
    TemplateBinding(
        "estate.first_publication_date",
        "estate_first_publication",
        "First publication of notice to creditors",
        "Estate dates",
    ),
    TemplateBinding(
        "estate.claims_bar_date",
        "estate_claims_bar_date",
        "Creditor claims bar date",
        "Estate dates",
    ),
    TemplateBinding(
        "estate.closing_statement_filed_date",
        "estate_closing_date",
        "Closing statement filed",
        "Estate dates",
    ),
    TemplateBinding(
        "estate.inventory_real_solely",
        "estate_inventory_real_solely",
        "Real property owned solely (total)",
        "Estate inventory",
    ),
    TemplateBinding(
        "estate.inventory_real_jointly",
        "estate_inventory_real_jointly",
        "Real property owned with others (total)",
        "Estate inventory",
    ),
    TemplateBinding(
        "estate.inventory_personal_solely",
        "estate_inventory_personal_solely",
        "Personal property owned solely (total)",
        "Estate inventory",
    ),
    TemplateBinding(
        "estate.inventory_personal_jointly",
        "estate_inventory_personal_jointly",
        "Personal property owned with others (total)",
        "Estate inventory",
    ),
    TemplateBinding(
        "estate.inventory_encumbrances",
        "estate_inventory_encumbrances",
        "Liens and encumbrances (total)",
        "Estate inventory",
    ),
    TemplateBinding(
        "estate.inventory_total",
        "estate_inventory_total",
        "Total value of estate assets",
        "Estate inventory",
    ),
    TemplateBinding(
        "estate.inventory_real_description",
        "estate_inventory_real_description",
        "Real property descriptions",
        "Estate inventory",
    ),
    TemplateBinding(
        "estate.inventory_personal_description",
        "estate_inventory_personal_description",
        "Personal property descriptions",
        "Estate inventory",
    ),
    # Item bindings resolve once per iteration of a repeating section, not from
    # the matter, so they have no alias: there is no single record behind them.
    TemplateBinding(
        "item.party_name", "", "Party name (this item)", "Repeating section"
    ),
    TemplateBinding(
        "item.party_role", "", "Party role (this item)", "Repeating section"
    ),
    TemplateBinding(
        "item.party_email", "", "Party email (this item)", "Repeating section"
    ),
    TemplateBinding(
        "item.party_phone", "", "Party phone (this item)", "Repeating section"
    ),
)

#: Prefix marking a binding that is resolved per repeat item.
ITEM_BINDING_PREFIX = "item."


def is_item_binding(path: str) -> bool:
    """Return whether a binding resolves per iteration of a repeating section."""

    return isinstance(path, str) and path.startswith(ITEM_BINDING_PREFIX)


def item_key(path: str) -> str:
    """Return the collection item field an item binding names."""

    return path[len(ITEM_BINDING_PREFIX) :] if is_item_binding(path) else ""


_BY_PATH: dict[str, TemplateBinding] = {entry.path: entry for entry in _CATALOGUE}


def catalogue() -> tuple[TemplateBinding, ...]:
    """Return every binding a customer may declare, in presentation order."""

    return _CATALOGUE


def is_valid_binding(path: str) -> bool:
    """Return whether ``path`` is the manual marker or a catalogue entry."""

    return (
        path == MANUAL_BINDING or path in _BY_PATH or custom_binding(path) is not None
    )


def alias_for_binding(path: str) -> str | None:
    """Return the Smart Fill candidate alias a binding resolves through.

    ``manual`` and unknown paths resolve to nothing: a manual field has no
    record behind it, and an unknown path must never fall through to a
    coincidental alias.
    """

    entry = _BY_PATH.get(path)
    return entry.alias if entry else None


def binding_label(path: str) -> str | None:
    """Return the human label for a binding, for provenance and UI copy."""

    if path == MANUAL_BINDING:
        return "Entered by hand"
    entry = _BY_PATH.get(path)
    return entry.label if entry else None


def declared_bindings(variable_schema: dict | None) -> dict[str, str]:
    """Return ``{field name: binding path}`` for every field that declares one.

    A path this catalogue no longer recognises is still returned, and still
    counts as declared. Save-time validation rejects unknown paths, so a stale
    one can only mean the catalogue itself changed under an existing template —
    and there the honest outcome is a blank field that names the source it can
    no longer reach. Quietly falling back to name matching would re-source a
    clause in a legal document without telling anyone.

    Tolerates malformed stored schemas: this runs on the read path for
    templates saved before bindings existed, so anything that is not a
    non-empty string on a named field is skipped rather than raising.
    """

    if not isinstance(variable_schema, dict):
        return {}
    fields = variable_schema.get("fields")
    if not isinstance(fields, list):
        return {}
    bindings: dict[str, str] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "").strip()
        binding = field.get("binding")
        if not name or not isinstance(binding, str) or not binding.strip():
            continue
        bindings[name] = binding.strip()
    return bindings


@dataclass(frozen=True)
class TemplateCollection:
    """One repeatable record set a ``{{#each}}`` block may iterate.

    ``item_fields`` are the placeholders available inside the block.  Keeping
    them declared rather than inferred means the editor can show a customer
    exactly what a repeating section can say before they write it.
    """

    name: str
    label: str
    item_fields: tuple[str, ...]


_COLLECTIONS: tuple[TemplateCollection, ...] = (
    TemplateCollection(
        "parties",
        "All matter parties",
        ("party_name", "party_role", "party_email", "party_phone"),
    ),
    TemplateCollection(
        "plaintiffs",
        "Plaintiffs",
        ("party_name", "party_role", "party_email", "party_phone"),
    ),
    TemplateCollection(
        "defendants",
        "Defendants",
        ("party_name", "party_role", "party_email", "party_phone"),
    ),
)

_COLLECTIONS_BY_NAME: dict[str, TemplateCollection] = {
    entry.name: entry for entry in _COLLECTIONS
}


def collections() -> tuple[TemplateCollection, ...]:
    """Return every collection a repeating section may iterate."""

    return _COLLECTIONS


def is_valid_collection(name: str) -> bool:
    """Return whether ``name`` is a known repeatable collection."""

    return name in _COLLECTIONS_BY_NAME


def custom_binding(path: str) -> tuple[str, str] | None:
    """A definition identity, never an expression or a customer-controlled path."""
    match = re.fullmatch(
        r"custom\.(matter|contact)\.([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        path or "",
    )
    return (match[1], match[2]) if match else None
