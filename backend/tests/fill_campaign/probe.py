"""The probe matter the approval gate used to learn Smart Fill's vocabulary.

Until the engine declared its aliases, ``_smart_fill_alias_vocabulary`` ran
the candidate builder over this fully populated stand-in and kept whatever
keys came out. It is preserved here as the oracle: the engine's declared
:func:`~app.services.template_fill_engine.vocabulary` must equal the set the
resolver actually writes for it, or a source is declaring something it never
produces (or producing something it never declared).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services import template_fill_engine
from app.services.probate import bindings as probate_bindings


def _contact() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        display_name="Probe",
        first_name="Probe",
        last_name="Person",
        preferred_name="P.",
        organization_name="Probe Org",
        entity_type="person",
        client_number="C-0",
        email="probe@example.com",
        phone="555-0100",
        address={
            "street": "1 Probe St",
            "city": "Probeville",
            "state": "PR",
            "zip": "00000",
            "country": "US",
        },
        date_of_birth="1970-01-01",
        secondary_phone="555-0101",
        preferred_contact_method="email",
        preferred_contact_window="Mornings",
        preferred_language="English",
        referral_source="Probe referral",
        emergency_contact={
            "name": "Probe Contact",
            "relationship": "Spouse",
            "phone": "555-0102",
            "email": "probe.contact@example.com",
        },
    )


def _party(role: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        is_primary=True,
        created_at="",
        contact=_contact(),
    )


def probe_matter() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        matter_name="Probe",
        matter_type="probe",
        description="Probe",
        status="open",
        stage="probe",
        jurisdiction="Probe",
        case_number="PR-0",
        court="Probe Court",
        judge="Probe Judge",
        billing_method="hourly",
        billing_cycle="monthly",
        hourly_rate=Decimal("1"),
        budget_amount=Decimal("1"),
        contingency_percentage=Decimal("1"),
        venue="Probe County",
        role="plaintiff",
        counterparty="Probe Counterparty",
        matter_number="PRB0001",
        practice_area="Probe practice",
        opened_on=date(2026, 1, 2),
        client=_contact(),
        attorney_of_record=SimpleNamespace(
            id=uuid.uuid4(), full_name="Probe Attorney", email="probe@firm.com"
        ),
    )


def probe_records(*, parties_per_role: int = 1) -> template_fill_engine.FillRecords:
    parties = []
    for role in template_fill_engine.PARTY_ROLES:
        parties.extend(_party(role) for _ in range(parties_per_role))
    return template_fill_engine.FillRecords(
        matter=probe_matter(),
        parties=parties,
        current_user=SimpleNamespace(
            id=uuid.uuid4(), full_name="Probe User", email="probe@user.com"
        ),
        retainer=SimpleNamespace(
            id=uuid.uuid4(), amount=Decimal("1"), minimum_balance=Decimal("1")
        ),
        estate=probate_bindings.probe_estate(),
    )


def probe_vocabulary() -> frozenset[str]:
    """What the old approval probe computed: every key the resolver writes.

    Synonyms are a resolver rule rather than a source, so they are added here
    the same way ``vocabulary`` adds them.
    """

    return frozenset(template_fill_engine.collect(probe_records())) | frozenset(
        template_fill_engine.NAME_SYNONYMS
    )
