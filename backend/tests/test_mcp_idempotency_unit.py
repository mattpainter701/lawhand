"""Request-level idempotency for billable Research MCP calls."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import mcp
from app.services.mcp_product import (
    normalize_idempotency_key,
    request_fingerprint,
)


def test_normalize_idempotency_key_trims_and_rejects_overlong() -> None:
    assert normalize_idempotency_key(None) is None
    assert normalize_idempotency_key("   ") is None
    assert normalize_idempotency_key("  retry-1  ") == "retry-1"

    with pytest.raises(HTTPException) as overlong:
        normalize_idempotency_key("x" * 201)
    assert overlong.value.status_code == 400


def test_request_fingerprint_is_stable_across_key_order() -> None:
    first = request_fingerprint("search_caselaw", {"query": "oil", "top_k": 2})
    reordered = request_fingerprint("search_caselaw", {"top_k": 2, "query": "oil"})

    assert first == reordered
    assert first != request_fingerprint("search_caselaw", {"query": "gas"})
    assert first != request_fingerprint(
        "search_legal_authorities", {"query": "oil", "top_k": 2}
    )


def test_credential_scope_separates_keys_grants_and_unknown() -> None:
    key = SimpleNamespace(id=uuid.uuid4())
    identity = SimpleNamespace(oauth_grant_id=str(uuid.uuid4()))

    assert mcp._credential_scope(key, None) == f"key:{key.id}"
    assert mcp._credential_scope(None, identity) == f"oauth:{identity.oauth_grant_id}"
    assert mcp._credential_scope(None, None) == "unknown"


def _product_request(idempotency_key: str | None) -> SimpleNamespace:
    headers = {"X-MCP-API-Key": "clmcp_test"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host="127.0.0.1"),
    )


@pytest.mark.asyncio
async def test_repeated_idempotency_key_is_rejected_without_second_billing(
    monkeypatch,
) -> None:
    tenant_id = uuid.uuid4()
    key_id = uuid.uuid4()
    product_key = SimpleNamespace(
        id=key_id,
        tenant_id=tenant_id,
        allowed_tools=["search_caselaw"],
        monthly_call_limit=100,
    )
    body = mcp.ToolCallRequest(name="search_caselaw", arguments={"query": "oil"})
    request = _product_request("retry-1")
    recorded: list[dict] = []
    proxy_calls: list[int] = []
    digest = request_fingerprint(body.name, body.arguments)
    stored: dict = {}

    async def resolve_key(*_args, **_kwargs):
        return product_key, SimpleNamespace(id=tenant_id)

    async def noop(*_args, **_kwargs):
        return None

    async def proxy(*_args, **_kwargs):
        proxy_calls.append(1)
        return {
            "content": [{"type": "json", "json": {"results": [{}]}}],
            "isError": False,
        }

    async def record_usage(**kwargs):
        recorded.append(kwargs)

    async def find(*_args, **_kwargs):
        return stored.get("event")

    monkeypatch.setattr(mcp.settings, "MCP_SERVER_URL", "http://courtlistener-mcp:8021")
    monkeypatch.setattr(mcp, "resolve_product_key", resolve_key)
    monkeypatch.setattr(mcp, "set_tenant_context", noop)
    monkeypatch.setattr(mcp, "enforce_product_key_burst_limit", noop)
    monkeypatch.setattr(mcp, "enforce_product_key_quota", noop)
    monkeypatch.setattr(mcp, "lock_mcp_idempotency_key", noop)
    monkeypatch.setattr(mcp, "_proxy_post", proxy)
    monkeypatch.setattr(mcp, "record_mcp_usage", record_usage)
    monkeypatch.setattr(mcp, "find_idempotent_usage_event", find)

    first = await mcp.call_tool(body, request, object())
    assert first["isError"] is False
    assert len(proxy_calls) == 1
    assert len(recorded) == 1
    usage = recorded[0]
    assert usage["request_idempotency_key"] == "retry-1"
    assert usage["credential_scope"] == f"key:{key_id}"
    assert usage["request_sha256"] == digest
    # Simulate the committed usage row the first call would have written.
    stored["event"] = SimpleNamespace(request_sha256=digest)

    with pytest.raises(HTTPException) as replay:
        await mcp.call_tool(body, request, object())
    assert replay.value.status_code == 409
    assert len(proxy_calls) == 1
    assert len(recorded) == 1


@pytest.mark.asyncio
async def test_idempotency_key_reuse_for_a_different_request_is_rejected(
    monkeypatch,
) -> None:
    tenant_id = uuid.uuid4()
    product_key = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        allowed_tools=["search_caselaw"],
        monthly_call_limit=100,
    )
    stored = SimpleNamespace(request_sha256="0" * 64)

    async def resolve_key(*_args, **_kwargs):
        return product_key, SimpleNamespace(id=tenant_id)

    async def noop(*_args, **_kwargs):
        return None

    async def find(*_args, **_kwargs):
        return stored

    monkeypatch.setattr(mcp, "resolve_product_key", resolve_key)
    monkeypatch.setattr(mcp, "set_tenant_context", noop)
    monkeypatch.setattr(mcp, "lock_mcp_idempotency_key", noop)
    monkeypatch.setattr(mcp, "find_idempotent_usage_event", find)

    with pytest.raises(HTTPException) as conflict:
        await mcp.call_tool(
            mcp.ToolCallRequest(name="search_caselaw", arguments={"query": "oil"}),
            _product_request("retry-1"),
            object(),
        )
    assert conflict.value.status_code == 409
