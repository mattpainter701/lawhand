import uuid

import pytest

from app.models.communication_log import CommunicationLog
from app.models.plugin import Matter
from app.services.correspondence_capture import (
    _already_captured,
    _eml_filename,
    _email_addresses,
    _internet_message_id,
    _matter_case_numbers,
    _matter_party_addresses,
    _resolve_rules,
    case_number_mentioned,
    evaluate_matter_rules,
    narrow_to_case_number_matches,
)

PARTY_EMAIL = "client@acme.com"


def _matter(case_number=None, rules=None):
    return Matter(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        slug="acme-v-globex",
        matter_name="Acme v. Globex",
        case_number=case_number,
        correspondence_rules=rules,
    )


# ── Address normalization ────────────────────────────────────────────────────


def test_email_addresses_handles_list_recipients():
    email = {
        "from": "Paralegal <para@firm.com>",
        "to": ["client@acme.com", "Attorney <atty@firm.com>"],
        "cc": [],
    }
    addrs = _email_addresses(email)
    assert addrs["from"] == "para@firm.com"
    assert set(addrs["to"]) == {"client@acme.com", "atty@firm.com"}
    assert "para@firm.com" in addrs["all"]


def test_email_addresses_handles_header_string():
    email = {"from": "client@acme.com", "to": "Atty <atty@firm.com>, para@firm.com"}
    addrs = _email_addresses(email)
    assert addrs["from"] == "client@acme.com"
    assert set(addrs["to"]) == {"atty@firm.com", "para@firm.com"}


# ── Rule evaluation ──────────────────────────────────────────────────────────


def test_party_address_match_captures():
    matter = _matter()
    rules = _resolve_rules(matter, force_enabled=True)
    email = {"from": PARTY_EMAIL, "to": ["atty@firm.com"], "subject": "Hello"}
    assert evaluate_matter_rules(matter, email, {PARTY_EMAIL}, rules) is True


def test_case_number_match_captures_without_party():
    matter = _matter(case_number="2024-CV-1234")
    rules = _resolve_rules(matter, force_enabled=True)
    email = {
        "from": "stranger@nowhere.com",
        "to": ["someone@else.com"],
        "subject": "Re: case 2024-CV-1234 status",
        "body_preview": "",
    }
    # No party addresses configured, but the case number appears in the subject.
    assert evaluate_matter_rules(matter, email, set(), rules) is True


def test_no_match_returns_false():
    matter = _matter(case_number="2024-CV-1234")
    rules = _resolve_rules(matter, force_enabled=True)
    email = {
        "from": "stranger@nowhere.com",
        "to": ["someone@else.com"],
        "subject": "Unrelated newsletter",
        "body_preview": "nothing relevant here",
    }
    assert evaluate_matter_rules(matter, email, {PARTY_EMAIL}, rules) is False


def test_disabled_rules_never_capture():
    matter = _matter(rules={"enabled": False, "match_parties": True})
    rules = _resolve_rules(matter)  # not force-enabled (scheduled path)
    email = {"from": PARTY_EMAIL, "to": ["atty@firm.com"], "subject": "Hello"}
    assert evaluate_matter_rules(matter, email, {PARTY_EMAIL}, rules) is False


def test_resolve_rules_force_enabled_overrides_disabled():
    matter = _matter(rules={"enabled": False})
    rules = _resolve_rules(matter, force_enabled=True)
    assert rules["enabled"] is True


def test_case_numbers_seed_from_matter_when_unset():
    matter = _matter(case_number="2024-CV-1234")
    rules = _resolve_rules(matter, force_enabled=True)
    assert _matter_case_numbers(matter, rules) == ["2024-CV-1234"]


def test_eml_filename_is_safe_and_dated():
    email = {"subject": "Re: Settlement / Offer!!", "received": "2024-03-01T10:00:00Z"}
    name = _eml_filename(email, "AAA-BBB-12345")
    assert name.startswith("2024-03-01_")
    assert name.endswith(".eml")
    assert "/" not in name and " " not in name


# ── Per-matter dedup (DB-backed) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_already_captured_is_per_matter(db_session, test_tenant, test_user):
    matter_a = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"matter-a-{uuid.uuid4().hex[:6]}",
        matter_name="Matter A",
    )
    matter_b = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"matter-b-{uuid.uuid4().hex[:6]}",
        matter_name="Matter B",
    )
    db_session.add_all([matter_a, matter_b])
    await db_session.commit()

    ref = "google:msg-abc-123"
    db_session.add(
        CommunicationLog(
            tenant_id=test_tenant.id,
            channel="email",
            direction="inbound",
            status="received",
            subject="Captured already",
            matter_id=matter_a.id,
            external_ref=ref,
        )
    )
    await db_session.commit()

    # Already captured for matter A, but not for matter B (same message id).
    assert (
        await _already_captured(db_session, test_tenant.id, matter_a.id, [ref]) is True
    )
    assert (
        await _already_captured(db_session, test_tenant.id, matter_b.id, [ref]) is False
    )


# ── Case-number precision ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "Re: 2024-CV-1234 status",
        "re: 2024 cv 1234 hearing",
        "Notice in case 2024.CV.1234.",
        "(2024-cv-1234)",
        "2024CV1234",
    ],
)
def test_case_number_matches_whole_number_with_any_separator(text):
    assert case_number_mentioned("2024-CV-1234", text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Re: 2024-CV-12345 status",  # a longer, different case number
        "Ref 12024-CV-1234",
        "phone 555-2024-CV-12349",
        "",
    ],
)
def test_case_number_does_not_match_inside_another_number(text):
    assert case_number_mentioned("2024-CV-1234", text) is False


def test_case_number_without_alphanumerics_never_matches():
    assert case_number_mentioned("--", "-- anything --") is False
    assert case_number_mentioned("", "anything") is False


def test_prefix_case_number_no_longer_captures_a_longer_one():
    matter = _matter(case_number="2024-CV-12")
    rules = _resolve_rules(matter, force_enabled=True)
    email = {
        "from": "clerk@court.gov",
        "to": ["atty@firm.com"],
        "subject": "Order entered in 2024-CV-1234",
    }
    assert evaluate_matter_rules(matter, email, set(), rules) is False


# ── Multi-matter fan-out ────────────────────────────────────────────────────


def test_case_number_narrows_a_client_with_several_matters():
    matter_a = _matter(case_number="2024-CV-1234")
    matter_b = _matter(case_number="2025-FA-0077")
    matched = [
        (matter_a, _resolve_rules(matter_a, force_enabled=True)),
        (matter_b, _resolve_rules(matter_b, force_enabled=True)),
    ]
    email = {"from": PARTY_EMAIL, "subject": "Question about 2025-FA-0077"}
    assert narrow_to_case_number_matches(matched, email) == [matched[1]]


def test_party_matches_stand_when_no_case_number_is_named():
    matter_a = _matter(case_number="2024-CV-1234")
    matter_b = _matter(case_number="2025-FA-0077")
    matched = [
        (matter_a, _resolve_rules(matter_a, force_enabled=True)),
        (matter_b, _resolve_rules(matter_b, force_enabled=True)),
    ]
    email = {"from": PARTY_EMAIL, "subject": "Quick question"}
    assert narrow_to_case_number_matches(matched, email) == matched


def test_single_match_is_never_narrowed_away():
    matter = _matter(case_number="2024-CV-1234")
    matched = [(matter, _resolve_rules(matter, force_enabled=True))]
    email = {"from": PARTY_EMAIL, "subject": "Unrelated"}
    assert narrow_to_case_number_matches(matched, email) == matched


# ── Cross-mailbox dedup ─────────────────────────────────────────────────────


def test_internet_message_id_is_trimmed_and_optional():
    assert _internet_message_id({"internet_message_id": " <a@b> "}) == "<a@b>"
    assert _internet_message_id({"internet_message_id": ""}) is None
    assert _internet_message_id({}) is None


@pytest.mark.asyncio
async def test_same_message_from_another_mailbox_is_already_captured(
    db_session, test_tenant, test_user
):
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"matter-dedup-{uuid.uuid4().hex[:6]}",
        matter_name="Dedup matter",
    )
    db_session.add(matter)
    await db_session.commit()
    matter_id = matter.id

    db_session.add(
        CommunicationLog(
            tenant_id=test_tenant.id,
            channel="email",
            direction="inbound",
            status="received",
            subject="Filed from the attorney's mailbox",
            matter_id=matter_id,
            external_ref="microsoft:attorney-mailbox-id",
            participants={"from": PARTY_EMAIL, "message_id": "<shared@acme.com>"},
        )
    )
    await db_session.commit()

    # The paralegal's copy has its own provider id but the same Message-ID.
    other_mailbox_refs = ["microsoft:paralegal-mailbox-id"]
    assert (
        await _already_captured(
            db_session,
            test_tenant.id,
            matter_id,
            other_mailbox_refs,
            "<shared@acme.com>",
        )
        is True
    )
    assert (
        await _already_captured(
            db_session,
            test_tenant.id,
            matter_id,
            other_mailbox_refs,
            "<different@acme.com>",
        )
        is False
    )
    assert (
        await _already_captured(db_session, test_tenant.id, matter_id, [], None)
        is False
    )


# ── Firm staff are not parties ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_party_addresses_exclude_staff_aliases(
    db_session, test_tenant, test_user
):
    from app.models.contact import Contact
    from app.models.matter_assignment import MatterAssignment
    from app.models.matter_party import MatterParty
    from app.models.user_alias import UserAliasAddress

    client = Contact(
        id=uuid.uuid4(), tenant_id=test_tenant.id, email="Client@Acme.com"
    )
    opposing = Contact(
        id=uuid.uuid4(), tenant_id=test_tenant.id, email="counsel@other.com"
    )
    db_session.add_all([client, opposing])
    await db_session.flush()
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"matter-parties-{uuid.uuid4().hex[:6]}",
        matter_name="Party matter",
        client_contact_id=client.id,
    )
    db_session.add(matter)
    await db_session.flush()
    db_session.add_all(
        [
            MatterParty(
                tenant_id=test_tenant.id,
                matter_id=matter.id,
                contact_id=opposing.id,
                role="opposing_counsel",
            ),
            MatterAssignment(
                tenant_id=test_tenant.id, matter_id=matter.id, user_id=test_user.id
            ),
            UserAliasAddress(
                tenant_id=test_tenant.id,
                user_id=test_user.id,
                address="Send-As@testfirm.com",
                normalized_address="send-as@testfirm.com",
                is_verified=True,
            ),
        ]
    )
    await db_session.commit()

    addresses = await _matter_party_addresses(db_session, test_tenant.id, matter)
    assert addresses == {"client@acme.com", "counsel@other.com"}


@pytest.mark.asyncio
async def test_participant_filter_ignores_the_stored_message_id(
    client, db_session, test_tenant, test_user
):
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"matter-filter-{uuid.uuid4().hex[:6]}",
        matter_name="Filter matter",
    )
    db_session.add(matter)
    await db_session.commit()
    matter_id = matter.id
    db_session.add(
        CommunicationLog(
            tenant_id=test_tenant.id,
            channel="email",
            direction="inbound",
            status="received",
            subject="From the client",
            matter_id=matter_id,
            external_ref="google:filter-1",
            participants={
                "from": PARTY_EMAIL,
                "to": ["attorney@testfirm.com"],
                "cc": [],
                "message_id": "<abc@mail.relay.example>",
            },
        )
    )
    await db_session.commit()

    url = f"/api/matters/{matter_id}/correspondence"
    by_address = await client.get(url, params={"participant": "acme.com"})
    assert by_address.status_code == 200
    assert by_address.json()["total"] == 1

    by_message_id = await client.get(url, params={"participant": "relay.example"})
    assert by_message_id.status_code == 200
    assert by_message_id.json()["total"] == 0
