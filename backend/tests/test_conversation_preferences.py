"""A conversation's tier and public-case-law preference, and who narrows it.

Regression cover for #487: both settings used to be per-message request fields
with nowhere to live, so closing and reopening a conversation silently reverted
the user's choice. These tests reopen a conversation and assert both settings,
including the case where firm policy narrows the stored choice.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.models.conversation import Conversation
from app.models.tenant import TenantSettings
from app.schemas.chat import MessageCreate
from app.services.public_case_law_policy import (
    resolve_include_public,
    tenant_public_case_law_allowed,
)


async def _set_public_case_law(db_session, tenant_id, allowed: bool) -> None:
    settings_row = TenantSettings(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        custom_config={"include_public_case_law": allowed},
    )
    db_session.add(settings_row)
    await db_session.commit()


@pytest.mark.asyncio
async def test_new_conversation_defaults_match_the_previous_in_memory_defaults(
    client: AsyncClient,
):
    conv = (await client.post("/api/conversations", json={"title": "Research"})).json()

    assert conv["use_premium_llm"] is False
    assert conv["include_public"] is True
    assert conv["public_case_law_restricted"] is False


@pytest.mark.asyncio
async def test_conversation_is_created_with_the_settings_the_user_had_selected(
    client: AsyncClient,
):
    conv = (
        await client.post(
            "/api/conversations",
            json={
                "title": "Premium, private",
                "use_premium_llm": True,
                "include_public": False,
            },
        )
    ).json()

    assert conv["use_premium_llm"] is True
    assert conv["include_public"] is False


@pytest.mark.asyncio
async def test_tier_and_public_case_law_survive_closing_and_reopening(
    client: AsyncClient,
):
    conv = (await client.post("/api/conversations", json={"title": "Research"})).json()

    patched = await client.patch(
        f"/api/conversations/{conv['id']}",
        json={"use_premium_llm": True, "include_public": False},
    )
    assert patched.status_code == 200
    assert patched.json()["use_premium_llm"] is True
    assert patched.json()["include_public"] is False

    # Reopening the conversation is the whole point of the issue: the stored
    # choice, not the component's defaults, is what comes back.
    reopened = (await client.get(f"/api/conversations/{conv['id']}")).json()
    assert reopened["conversation"]["use_premium_llm"] is True
    assert reopened["conversation"]["include_public"] is False

    listed = (await client.get("/api/conversations")).json()
    stored = next(item for item in listed if item["id"] == conv["id"])
    assert stored["use_premium_llm"] is True
    assert stored["include_public"] is False


@pytest.mark.asyncio
async def test_preference_only_patch_is_accepted_without_a_title_or_matter(
    client: AsyncClient,
):
    conv = (await client.post("/api/conversations", json={"title": "Research"})).json()

    resp = await client.patch(
        f"/api/conversations/{conv['id']}", json={"include_public": False}
    )

    assert resp.status_code == 200
    assert resp.json()["title"] == "Research"
    assert resp.json()["include_public"] is False


@pytest.mark.asyncio
async def test_empty_patch_is_still_rejected(client: AsyncClient):
    conv = (await client.post("/api/conversations", json={"title": "Research"})).json()

    resp = await client.patch(f"/api/conversations/{conv['id']}", json={})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_firm_policy_narrows_a_stored_public_case_law_preference(
    client: AsyncClient, db_session, test_tenant
):
    await _set_public_case_law(db_session, test_tenant.id, False)

    conv = (
        await client.post(
            "/api/conversations",
            json={"title": "Research", "include_public": True},
        )
    ).json()

    # The user's own choice is still what is stored — firm policy narrows the
    # request, it does not overwrite the preference — and the restriction is
    # reported so the UI can explain the difference.
    assert conv["include_public"] is True
    assert conv["public_case_law_restricted"] is True

    reopened = (await client.get(f"/api/conversations/{conv['id']}")).json()
    assert reopened["conversation"]["include_public"] is True
    assert reopened["conversation"]["public_case_law_restricted"] is True


@pytest.mark.asyncio
async def test_firm_policy_can_only_narrow_never_widen(db_session, test_tenant):
    await _set_public_case_law(db_session, test_tenant.id, False)

    assert await tenant_public_case_law_allowed(db_session, test_tenant.id) is False
    assert await resolve_include_public(db_session, test_tenant.id, True) is False
    # A conversation that asked to stay private stays private whatever the
    # firm permits.
    assert await resolve_include_public(db_session, test_tenant.id, False) is False


@pytest.mark.asyncio
async def test_missing_or_malformed_tenant_settings_leave_public_case_law_on(
    db_session, test_tenant
):
    assert await tenant_public_case_law_allowed(db_session, test_tenant.id) is True

    settings_row = TenantSettings(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        custom_config=None,
    )
    db_session.add(settings_row)
    await db_session.commit()

    assert await tenant_public_case_law_allowed(db_session, test_tenant.id) is True


@pytest.mark.asyncio
async def test_sending_records_the_choice_and_runs_with_the_narrowed_one(
    db_session, test_tenant, test_user
):
    from app.routers.chat import _apply_conversation_preferences

    await _set_public_case_law(db_session, test_tenant.id, False)
    conv = Conversation(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        title="Research",
    )
    db_session.add(conv)
    await db_session.commit()

    body = MessageCreate(content="What is the standard?", include_public=True)
    await _apply_conversation_preferences(db_session, test_user, conv, body)

    assert conv.include_public is True  # what the user asked for, stored
    assert body.include_public is False  # what this turn actually runs with


@pytest.mark.asyncio
async def test_me_reports_the_firm_public_case_law_policy(
    client: AsyncClient, db_session, test_tenant
):
    allowed = (await client.get("/api/auth/me")).json()
    assert allowed["public_case_law_allowed"] is True

    await _set_public_case_law(db_session, test_tenant.id, False)

    restricted = (await client.get("/api/auth/me")).json()
    assert restricted["public_case_law_allowed"] is False
