"""Provider-independent streaming checks for both customer gateway aliases."""

import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.services import llm as llm_module


@pytest.mark.asyncio
async def test_streaming_routes_both_aliases_and_uses_private_litellm_metadata(
    monkeypatch,
):
    requests: list[dict] = []

    async def fake_gateway(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.url.path == "/v1/chat/completions"
        assert payload["stream"] is True
        assert payload.get("metadata") is None
        assert payload["litellm_metadata"] == {
            "tenant_id": "tenant-ci",
            "matter_id": "matter-ci",
        }
        events = [
            {
                "id": "ci",
                "object": "chat.completion.chunk",
                "model": payload["model"],
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "streamed"},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "ci",
                "object": "chat.completion.chunk",
                "model": payload["model"],
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": " response"},
                        "finish_reason": "stop",
                    }
                ],
            },
        ]
        body = (
            "".join(f"data: {json.dumps(event)}\n\n" for event in events)
            + "data: [DONE]\n\n"
        )
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=body.encode()
        )

    standard_alias = "lawhand-standard"
    premium_alias = "lawhand-premium"
    monkeypatch.setattr(llm_module.settings, "LITELLM_STANDARD_MODEL", standard_alias)
    monkeypatch.setattr(llm_module.settings, "LITELLM_PREMIUM_MODEL", premium_alias)
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(fake_gateway), base_url="http://gateway/v1"
    )
    service = llm_module.LLMService()
    service.client = AsyncOpenAI(
        api_key="sk-ci-contract", base_url="http://gateway/v1", http_client=http_client
    )
    try:
        kwargs = {
            "messages": [{"role": "user", "content": "health check"}],
            "tenant_name": "CI tenant",
            "context": "",
            "gateway_metadata": {"tenant_id": "tenant-ci", "matter_id": "matter-ci"},
            "system_prompt_override": "Return only the health-check response.",
        }
        standard = "".join([chunk async for chunk in service.stream_complete(**kwargs)])
        premium = "".join(
            [
                chunk
                async for chunk in service.stream_complete(**kwargs, use_premium=True)
            ]
        )
    finally:
        await service.client.close()
    assert standard == "streamed response"
    assert premium == "streamed response"
    assert [payload["model"] for payload in requests] == [standard_alias, premium_alias]


def _sse(events: list[dict]) -> bytes:
    return (
        "".join(f"data: {json.dumps(event)}\n\n" for event in events)
        + "data: [DONE]\n\n"
    ).encode()


def _empty_visible_events(model: str) -> list[dict]:
    """A 200 stream that carries only hidden reasoning and no visible content."""
    return [
        {
            "id": "ci",
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"reasoning_content": "hidden chain of thought"},
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": "ci",
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "length"}],
        },
        {
            "id": "ci",
            "object": "chat.completion.chunk",
            "choices": [],
            "usage": {"prompt_tokens": 5, "completion_tokens": 40, "total_tokens": 45},
        },
    ]


def _visible_events(model: str) -> list[dict]:
    return [
        {
            "id": "ci",
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "recovered answer"},
                    "finish_reason": "stop",
                }
            ],
        }
    ]


def _service_with_gateway(handler) -> llm_module.LLMService:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gateway/v1"
    )
    service = llm_module.LLMService()
    service.client = AsyncOpenAI(
        api_key="sk-ci-contract", base_url="http://gateway/v1", http_client=http_client
    )
    return service


@pytest.mark.asyncio
async def test_empty_visible_stream_is_retried_with_a_larger_budget(monkeypatch):
    """A 200 with no visible token must not fail the turn on the first try.

    LiteLLM only falls back on provider errors, so an empty successful stream
    has no gateway-level recovery. The service retries once with a larger
    output budget so hidden reasoning cannot starve the visible answer.
    """
    requests: list[dict] = []

    async def fake_gateway(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        events = (
            _empty_visible_events(payload["model"])
            if len(requests) == 1
            else _visible_events(payload["model"])
        )
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse(events)
        )

    monkeypatch.setattr(
        llm_module.settings, "LITELLM_STANDARD_MODEL", "lawhand-standard"
    )
    service = _service_with_gateway(fake_gateway)
    usage: dict = {}
    try:
        chunks = [
            chunk
            async for chunk in service.stream_complete(
                messages=[{"role": "user", "content": "hi"}],
                tenant_name="CI tenant",
                context="",
                gateway_metadata={"tenant_id": "tenant-ci"},
                system_prompt_override="Answer the question.",
                usage_sink=usage,
            )
        ]
    finally:
        await service.client.close()

    assert "".join(chunks) == "recovered answer"
    assert len(requests) == 2
    assert requests[1]["max_tokens"] > requests[0]["max_tokens"]
    assert requests[0]["model"] == requests[1]["model"] == "lawhand-standard"
    assert usage["model"] == "lawhand-standard"
    assert usage["provider_stream_ms"] >= 0
    assert requests[0]["litellm_metadata"] == {"tenant_id": "tenant-ci"}


@pytest.mark.asyncio
async def test_stream_falls_back_to_the_next_candidate_before_first_token(monkeypatch):
    """A provider error before any token still uses the gateway's next route."""
    requests: list[dict] = []
    aliases = ["lawhand-standard", "lawhand-standard-deepseek-flash-free"]

    async def fake_gateway(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            # 400 is an APIError the SDK does not retry itself.
            return httpx.Response(400, json={"error": {"message": "bad route"}})
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(_visible_events(payload["model"])),
        )

    monkeypatch.setattr(
        llm_module.settings, "LITELLM_STANDARD_MODEL", "lawhand-standard"
    )
    monkeypatch.setattr(
        llm_module.LLMService,
        "_gateway_candidates",
        lambda self, *args, **kwargs: list(aliases),
    )
    service = _service_with_gateway(fake_gateway)
    try:
        chunks = [
            chunk
            async for chunk in service.stream_complete(
                messages=[{"role": "user", "content": "hi"}],
                tenant_name="CI tenant",
                context="",
                system_prompt_override="Answer the question.",
            )
        ]
    finally:
        await service.client.close()

    assert "".join(chunks) == "recovered answer"
    assert [payload["model"] for payload in requests] == aliases


@pytest.mark.asyncio
async def test_empty_visible_stream_fails_after_a_bounded_retry(monkeypatch):
    requests: list[dict] = []

    async def fake_gateway(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(_empty_visible_events(payload["model"])),
        )

    monkeypatch.setattr(
        llm_module.settings, "LITELLM_STANDARD_MODEL", "lawhand-standard"
    )
    service = _service_with_gateway(fake_gateway)
    try:
        with pytest.raises(RuntimeError, match="no visible answer"):
            [
                chunk
                async for chunk in service.stream_complete(
                    messages=[{"role": "user", "content": "hi"}],
                    tenant_name="CI tenant",
                    context="",
                    system_prompt_override="Answer the question.",
                )
            ]
    finally:
        await service.client.close()

    # Exactly one retry: a genuinely empty model cannot multiply latency or spend.
    assert len(requests) == llm_module._EMPTY_RESPONSE_ATTEMPTS
