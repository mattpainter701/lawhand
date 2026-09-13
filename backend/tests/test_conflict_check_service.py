"""Conflict-search matching regressions.

A conflict search must fail toward attorney review, never toward clearance, so
these cover the ways a real name is typed: reversed, comma-separated, or with a
middle name the contact record does not carry.
"""

import json
import uuid

import pytest

from app.models.contact import Contact
from app.models.plugin import Matter
from app.routers.conflict_checks import ZERO_UUID
from app.services.conflict_check import run_conflict_check


def _contact(tenant_id, **fields):
    return Contact(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        entity_type=fields.pop("entity_type", "person"),
        contact_type=fields.pop("contact_type", "client"),
        is_active=fields.pop("is_active", True),
        **fields,
    )


def _matter(tenant_id, user_id, matter_name, **fields):
    return Matter(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        slug=f"matter-{uuid.uuid4().hex[:10]}",
        matter_name=matter_name,
        matter_type="litigation",
        **fields,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "term",
    ["Alice Smith", "Smith, Alice", "smith alice", "Alice Marie Smith"],
)
async def test_full_name_search_tolerates_order_separators_and_middle_names(
    db_session, test_tenant, test_user, term
):
    alice = _contact(
        test_tenant.id, first_name="Alice", last_name="Smith", email="alice@example.com"
    )
    # Shares only the first name, so a single overlapping word must not hit.
    unrelated = _contact(
        test_tenant.id, first_name="Alice", last_name="Jones", email="aj@example.com"
    )
    retired = _contact(
        test_tenant.id,
        first_name="Alice",
        last_name="Smith",
        email="retired@example.com",
        is_active=False,
    )
    db_session.add_all([alice, unrelated, retired])
    await db_session.flush()
    matter = _matter(
        test_tenant.id, test_user.id, "Acme v. Smith", client_contact_id=alice.id
    )
    db_session.add(matter)
    await db_session.commit()

    result = await run_conflict_check(db_session, test_tenant.id, [term], [])

    assert result["clear"] is False
    assert [match["contact_id"] for match in result["matches"]] == [alice.id]
    assert result["matches"][0]["matter_names"] == ["Acme v. Smith"]
    assert result["matches"][0]["match_value"] == term


@pytest.mark.asyncio
async def test_one_shared_word_is_not_reported_as_a_conflict(
    db_session, test_tenant, test_user
):
    db_session.add(
        _contact(
            test_tenant.id,
            first_name="Alice",
            last_name="Smith",
            email="alice@example.com",
        )
    )
    await db_session.commit()

    result = await run_conflict_check(db_session, test_tenant.id, ["Alice Jones"], [])

    assert result == {"clear": True, "matches": []}


@pytest.mark.asyncio
async def test_counterparty_conflict_surfaces_on_a_matter_that_has_a_client(
    db_session, test_tenant, test_user
):
    client = _contact(
        test_tenant.id, first_name="Dana", last_name="Reed", email="dana@example.com"
    )
    db_session.add(client)
    await db_session.flush()
    matter = _matter(
        test_tenant.id,
        test_user.id,
        "Reed v. Acme",
        client_contact_id=client.id,
        counterparty="Acme Holdings LLC",
    )
    db_session.add(matter)
    await db_session.commit()

    result = await run_conflict_check(
        db_session, test_tenant.id, [], [], organization_names=["Acme Holdings"]
    )

    assert result["clear"] is False
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert match["match_field"] == "matter_counterparty"
    assert match["contact_id"] == ZERO_UUID
    assert match["display_name"] == "Acme Holdings LLC"
    assert match["matter_ids"] == [matter.id]


@pytest.mark.asyncio
async def test_counterparty_matter_is_listed_once_when_a_contact_also_matches(
    db_session, test_tenant, test_user
):
    acme = _contact(
        test_tenant.id,
        entity_type="organization",
        contact_type="opposing_party",
        organization_name="Acme Holdings LLC",
    )
    db_session.add(acme)
    await db_session.flush()
    matter = _matter(
        test_tenant.id, test_user.id, "Reed v. Acme", counterparty="Acme Holdings LLC"
    )
    db_session.add(matter)
    await db_session.commit()

    result = await run_conflict_check(
        db_session, test_tenant.id, [], [], organization_names=["Acme Holdings"]
    )

    assert len(result["matches"]) == 1
    assert result["matches"][0]["contact_id"] == acme.id
    assert result["matches"][0]["matter_ids"] == [matter.id]


@pytest.mark.asyncio
async def test_excluded_matters_stay_out_of_counterparty_results(
    db_session, test_tenant, test_user
):
    matter = _matter(
        test_tenant.id, test_user.id, "Reed v. Acme", counterparty="Acme Holdings LLC"
    )
    db_session.add(matter)
    await db_session.commit()

    result = await run_conflict_check(
        db_session,
        test_tenant.id,
        [],
        [],
        organization_names=["Acme Holdings"],
        exclude_matter_ids=[matter.id],
    )

    assert result == {"clear": True, "matches": []}


@pytest.mark.asyncio
async def test_wildcard_characters_do_not_widen_the_search(
    db_session, test_tenant, test_user
):
    db_session.add(
        _contact(
            test_tenant.id,
            first_name="Alice",
            last_name="Smith",
            email="alice@example.com",
        )
    )
    await db_session.commit()

    result = await run_conflict_check(db_session, test_tenant.id, ["%"], ["_"])

    assert result == {"clear": True, "matches": []}


@pytest.mark.asyncio
async def test_conflict_check_route_withholds_matters_the_viewer_is_not_on(
    client, db_session, test_tenant, test_user
):
    """The legacy route returned raw matches with no assignment-aware redaction.

    Broadening counterparty matching turned that into a way for any signed-in
    user to probe for the names of matters they are not assigned to.
    """
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.config import get_settings
    from app.models.user import User

    settings = get_settings()

    other_user = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="associate@testfirm.com",
        full_name="Unassigned Associate",
        role="attorney",
        oauth_provider="google",
        oauth_subject=f"google-{uuid.uuid4().hex[:12]}",
        is_active=True,
    )
    acme = _contact(
        test_tenant.id,
        entity_type="organization",
        contact_type="opposing_party",
        organization_name="Acme Holdings LLC",
    )
    db_session.add_all([other_user, acme])
    await db_session.flush()
    hidden = _matter(
        test_tenant.id,
        test_user.id,
        "Confidential merger dispute",
        counterparty="Acme Holdings LLC",
    )
    db_session.add(hidden)
    await db_session.commit()

    token = jwt.encode(
        {
            "sub": str(other_user.id),
            "tenant_id": str(test_tenant.id),
            "role": "attorney",
            "email": other_user.email,
            "billing_tier": "payg",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = await client.post(
        "/api/contacts/conflict-check",
        json={"names": [], "emails": [], "organization_names": ["Acme Holdings"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    serialized = json.dumps(body)
    assert "Confidential merger dispute" not in serialized
    assert str(hidden.id) not in serialized
    assert body["restricted_matter_count"] >= 1


@pytest.mark.asyncio
async def test_conflict_check_route_shows_an_admin_the_whole_match(
    client, db_session, test_tenant, test_user
):
    acme = _contact(
        test_tenant.id,
        entity_type="organization",
        contact_type="opposing_party",
        organization_name="Acme Holdings LLC",
    )
    db_session.add(acme)
    await db_session.flush()
    matter = _matter(
        test_tenant.id,
        test_user.id,
        "Acme merger dispute",
        counterparty="Acme Holdings LLC",
    )
    db_session.add(matter)
    await db_session.commit()

    response = await client.post(
        "/api/contacts/conflict-check",
        json={"names": [], "emails": [], "organization_names": ["Acme Holdings"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["restricted_matter_count"] == 0
    assert "Acme merger dispute" in json.dumps(body)
