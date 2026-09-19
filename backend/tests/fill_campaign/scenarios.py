"""Mock matters for the fill campaign.

Each scenario is the in-memory shape the resolver reads (the same duck-typed
objects ``test_template_binding_smart_fill`` uses) plus, for the database lane,
a ``persist`` that writes the equivalent ORM rows.  The two must describe the
same people so a route-level run and an in-memory run of one scenario can be
compared field for field.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any


@dataclass
class Scenario:
    key: str
    description: str
    matter: Any
    parties: list = field(default_factory=list)
    retainer: Any = None
    estate: Any = None
    #: The firm profile ``firm.*`` bindings read, as the branding dict the
    #: resolver sees; ``{}`` means nothing is configured.
    firm: dict[str, str] = field(default_factory=dict)
    #: ``{binding path: value}`` for ``custom.matter.<id>`` bindings.
    custom_fields: dict[str, str] = field(default_factory=dict)
    #: What a reader should expect from this scenario, by field name. Used by
    #: the report to annotate a blank as "expected: no source" rather than a
    #: regression.
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def matter_id(self) -> str | None:
        return str(self.matter.id) if self.matter is not None else None


def current_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), full_name="Grace Hopper", email="grace@firm.example"
    )


def _contact(
    *,
    first_name: str | None,
    last_name: str | None,
    organization_name: str | None = None,
    entity_type: str = "person",
    email: str | None = None,
    phone: str | None = None,
    address: dict | None = None,
    **extra,
) -> SimpleNamespace:
    if entity_type == "organization" and organization_name:
        display = organization_name
    else:
        display = " ".join(part for part in (first_name, last_name) if part)
    return SimpleNamespace(
        id=uuid.uuid4(),
        entity_type=entity_type,
        first_name=first_name,
        last_name=last_name,
        preferred_name=None,
        organization_name=organization_name,
        display_name=display,
        email=email,
        phone=phone,
        address=address,
        date_of_birth=extra.get("date_of_birth"),
        secondary_phone=None,
        preferred_contact_method=extra.get("preferred_contact_method"),
        preferred_contact_window=None,
        preferred_language=None,
        referral_source=None,
        emergency_contact=None,
        client_number=extra.get("client_number"),
    )


def _party(role: str, contact: SimpleNamespace, *, is_primary=False, day=1):
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        is_primary=is_primary,
        created_at=datetime(2026, 1, day, tzinfo=timezone.utc),
        contact=contact,
    )


def _matter(**overrides) -> SimpleNamespace:
    base = dict(
        id=uuid.uuid4(),
        matter_number="LOV0001",
        matter_name="Lovelace v. Analytical Engines",
        matter_type="civil",
        practice_area="Commercial Litigation",
        description="Breach of a software licence.",
        status="open",
        stage="pleadings",
        jurisdiction="North Dakota",
        venue="Cass County",
        case_number="08-2026-CV-00042",
        court="Cass County District Court",
        judge="Hon. A. Turing",
        billing_method="hourly",
        billing_cycle="monthly",
        hourly_rate=Decimal("250.00"),
        budget_amount=Decimal("15000"),
        contingency_percentage=None,
        opened_on=date(2026, 3, 4),
        role="plaintiff",
        counterparty="Analytical Engines LLC",
        client=None,
        attorney_of_record=SimpleNamespace(
            id=uuid.uuid4(), full_name="Ada Byron", email="ada@firm.example"
        ),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def individual_client() -> Scenario:
    """A person client, plaintiff side, hourly with a retainer."""

    client = _contact(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        phone="701-555-0100",
        address={
            "street": "12 Engine St",
            "city": "Fargo",
            "state": "ND",
            "zip": "58102",
            "country": "US",
        },
        date_of_birth=date(1985, 12, 10),
        client_number="C-1001",
    )
    matter = _matter(client=client)
    retainer = SimpleNamespace(
        id=uuid.uuid4(),
        amount=Decimal("5000.00"),
        minimum_balance=Decimal("1000.00"),
        status="active",
    )
    return Scenario(
        key="individual_client",
        description="Person client, plaintiff side, hourly, active retainer, no party rows",
        matter=matter,
        retainer=retainer,
        firm={
            "firm_name": "Hopper & Byron LLP",
            "firm_address": "100 Main Ave, Fargo, ND 58102",
            "firm_phone": "701-555-0000",
            "firm_email": "office@firm.example",
            "firm_website": "https://firm.example",
        },
        notes={
            "first_name": "no source: contact.first_name is not exposed",
            "last_name": "no source: contact.last_name is not exposed",
            "matter_number": "no source: matter.matter_number is not exposed",
            "opened_on": "no source: matter.opened_on is not exposed",
            "plaintiff_name": "inferred from matter.role + client at 0.75",
            "defendant_name": "inferred from matter.counterparty at 0.75",
        },
    )


def entity_client() -> Scenario:
    """An organization client on the defendant side, contingency billing."""

    client = _contact(
        first_name=None,
        last_name=None,
        organization_name="Babbage Holdings LLC",
        entity_type="organization",
        email="legal@babbage.example",
        phone="701-555-0200",
        address={
            "street": "1 Difference Way",
            "city": "Bismarck",
            "state": "ND",
            "zip": "58501",
        },
    )
    matter = _matter(
        matter_name="Menabrea v. Babbage Holdings",
        matter_type="litigation",
        practice_area="Commercial Litigation",
        billing_method="contingency",
        billing_cycle=None,
        hourly_rate=None,
        contingency_percentage=Decimal("33.3"),
        role="defendant",
        counterparty="Luigi Menabrea",
        client=client,
    )
    return Scenario(
        key="entity_client",
        description="Organization client, defendant side, contingency, no party rows",
        matter=matter,
        notes={
            "client_first_name": "no source: an organization has no first name",
            "defendant_name": "inferred from matter.role + client at 0.75",
            "plaintiff_name": "inferred from matter.counterparty at 0.75",
        },
    )


def family_petitioner() -> Scenario:
    """A family-law matter whose caption is petitioner/respondent."""

    client = _contact(
        first_name="Mary",
        last_name="Somerville",
        email="mary@example.com",
        phone="701-555-0300",
        address={
            "street": "8 Orbit Rd",
            "city": "Grand Forks",
            "state": "ND",
            "zip": "58201",
        },
    )
    respondent = _contact(
        first_name="William",
        last_name="Somerville",
        email="will@example.com",
        phone="701-555-0301",
        address={"city": "Grand Forks", "state": "ND"},
    )
    matter = _matter(
        matter_name="In re Marriage of Somerville",
        matter_type="general",
        practice_area="Family Law",
        role="petitioner",
        counterparty="William Somerville",
        case_number="18-2026-DM-00007",
        client=client,
    )
    return Scenario(
        key="family_petitioner",
        description="Family law: petitioner/respondent party rows, matter.role=petitioner",
        matter=matter,
        parties=[
            _party("petitioner", client, is_primary=True, day=1),
            _party("respondent", respondent, day=2),
        ],
        notes={
            "petitioner_name": "no source: only plaintiff/defendant roles emit aliases",
            "respondent_name": "no source: only plaintiff/defendant roles emit aliases",
            "plaintiff_name": "no source: role 'petitioner' is not a plaintiff",
        },
    )


def probate_estate() -> Scenario:
    """A probate matter linked to a fully populated estate record."""

    from app.services.probate import bindings as probate_bindings

    client = _contact(
        first_name="Probe",
        last_name="Applicant",
        email="probe@example.com",
        phone="701-555-0100",
        address={
            "street": "1 Probe St",
            "city": "Fargo",
            "state": "ND",
            "zip": "58102",
        },
    )
    matter = _matter(
        matter_name="Estate of Probe Decedent",
        matter_type="probate",
        practice_area="Trusts, Estates & Probate",
        role=None,
        counterparty=None,
        case_number="08-2025-PR-00001",
        client=client,
    )
    return Scenario(
        key="probate_estate",
        description="Probate matter with a linked estate (estate.* bindings resolvable)",
        matter=matter,
        estate=probate_bindings.probe_estate(),
        notes={
            "estate_decedent_name": (
                "unbound: the estate loads only for an estate.* binding, so a "
                "name match is reported as filling but resolves to nothing"
            ),
        },
    )


def sparse() -> Scenario:
    """The minimum a matter can be: a name and nothing else."""

    matter = _matter(
        matter_name="New Matter",
        matter_number=None,
        matter_type=None,
        practice_area=None,
        description=None,
        stage=None,
        jurisdiction=None,
        venue=None,
        case_number=None,
        court=None,
        judge=None,
        billing_method=None,
        billing_cycle=None,
        hourly_rate=None,
        budget_amount=None,
        opened_on=None,
        role=None,
        counterparty=None,
        client=None,
        attorney_of_record=None,
    )
    return Scenario(
        key="sparse",
        description="Matter with a name only: every other field should be blank, not wrong",
        matter=matter,
    )


def two_defendants() -> Scenario:
    """Two defendants and one plaintiff as structured party rows."""

    plaintiff = _contact(
        first_name="Ada", last_name="Lovelace", email="ada@example.com"
    )
    first = _contact(
        first_name=None,
        last_name=None,
        organization_name="Analytical Engines LLC",
        entity_type="organization",
        email="service@engines.example",
    )
    second = _contact(
        first_name="Charles", last_name="Babbage", email="charles@example.com"
    )
    matter = _matter(
        client=plaintiff, role="plaintiff", counterparty="Ignored Counterparty"
    )
    return Scenario(
        key="two_defendants",
        description="Structured plaintiff and two defendants; instance aliases in play",
        matter=matter,
        parties=[
            _party("plaintiff", plaintiff, is_primary=True, day=1),
            _party("defendant", first, is_primary=True, day=2),
            _party("defendant", second, day=3),
        ],
        notes={
            "defendant_name": "primary defendant row wins over matter.counterparty",
            "defendant_2_full_name": "second defendant via instance alias",
        },
    )


def all_scenarios() -> list[Scenario]:
    return [
        individual_client(),
        entity_client(),
        family_petitioner(),
        probate_estate(),
        sparse(),
        two_defendants(),
    ]


async def persist(db, tenant_id, user_id, scenario: Scenario) -> dict[str, Any]:
    """Write the scenario's people as ORM rows; return their ids.

    Only the pieces the resolver reads are written: the client contact, the
    matter, party rows and the current retainer.  The estate is left in memory;
    the route test does not exercise it.
    """

    from app.models.contact import Contact
    from app.models.matter_party import MatterParty
    from app.models.plugin import Matter
    from app.models.retainer import Retainer

    def contact_row(mock) -> Contact:
        return Contact(
            id=mock.id,
            tenant_id=tenant_id,
            entity_type=mock.entity_type,
            contact_type="client",
            first_name=mock.first_name,
            last_name=mock.last_name,
            organization_name=mock.organization_name,
            email=mock.email,
            phone=mock.phone,
            address=mock.address,
            date_of_birth=mock.date_of_birth,
        )

    source = scenario.matter
    contacts: dict[uuid.UUID, Contact] = {}
    if source.client is not None:
        contacts[source.client.id] = contact_row(source.client)
    for party in scenario.parties:
        contacts.setdefault(party.contact.id, contact_row(party.contact))
    for row in contacts.values():
        db.add(row)
    await db.flush()

    matter = Matter(
        id=source.id,
        tenant_id=tenant_id,
        user_id=user_id,
        slug=f"campaign-{uuid.uuid4().hex[:8]}",
        matter_name=source.matter_name,
        matter_type=source.matter_type or "general",
        practice_area=source.practice_area,
        description=source.description,
        status=source.status or "open",
        stage=source.stage,
        jurisdiction=source.jurisdiction,
        venue=source.venue,
        case_number=source.case_number,
        court=source.court,
        judge=source.judge,
        billing_method=source.billing_method or "hourly",
        billing_cycle=source.billing_cycle,
        hourly_rate=source.hourly_rate,
        budget_amount=source.budget_amount,
        opened_on=source.opened_on,
        role=source.role,
        counterparty=source.counterparty,
        client_contact_id=source.client.id if source.client is not None else None,
        attorney_of_record_id=None,
    )
    db.add(matter)
    await db.flush()
    for party in scenario.parties:
        db.add(
            MatterParty(
                id=party.id,
                tenant_id=tenant_id,
                matter_id=matter.id,
                contact_id=party.contact.id,
                role=party.role,
                is_primary=party.is_primary,
                created_at=party.created_at,
            )
        )
    if scenario.retainer is not None and source.client is not None:
        db.add(
            Retainer(
                id=scenario.retainer.id,
                tenant_id=tenant_id,
                matter_id=matter.id,
                contact_id=source.client.id,
                retainer_type="standard",
                amount=scenario.retainer.amount,
                current_balance=scenario.retainer.amount,
                minimum_balance=scenario.retainer.minimum_balance,
                status=scenario.retainer.status,
            )
        )
    await db.commit()
    return {
        "matter_id": str(matter.id),
        "contact_ids": [str(key) for key in contacts],
        "party_ids": [str(party.id) for party in scenario.parties],
    }
