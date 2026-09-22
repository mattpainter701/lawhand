"""Focused tests for the admin cloud-search diagnostic contract."""

from app.routers.cloud_admin import _CloudSearchTestRequest, _diagnostic_plan
import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from app.routers import cloud_admin


def test_exact_diagnostic_preserves_filename_and_selected_source() -> None:
    body = _CloudSearchTestRequest(
        query="QA PDF Fixture 2026-09-22-d1245828.pdf",
        sources=["onedrive"],
        exact_query=True,
        max_hits=3,
    )

    assert _diagnostic_plan(body, {"should_search": True, "keywords": ["QA"]}) == {
        "should_search": True,
        "sources": ["onedrive"],
        "keywords": ["QA PDF Fixture 2026-09-22-d1245828.pdf"],
        "date_after": "",
        "max_hits": 3,
        "exact_query": True,
    }


def test_normal_diagnostic_keeps_planner_keywords_but_overrides_scope() -> None:
    body = _CloudSearchTestRequest(
        query="latest renewal discussion",
        sources=["outlook"],
        max_hits=7,
    )
    planner_plan = {
        "should_search": True,
        "sources": ["gmail"],
        "keywords": ["renewal", "discussion"],
    }

    assert _diagnostic_plan(body, planner_plan) == {
        "should_search": True,
        "sources": ["outlook"],
        "keywords": ["renewal", "discussion"],
        "max_hits": 7,
    }


def test_normal_diagnostic_preserves_no_search_plan() -> None:
    body = _CloudSearchTestRequest(query="general question", sources=["outlook"])
    planner_plan = {"should_search": False, "sources": [], "keywords": []}

    assert _diagnostic_plan(body, planner_plan) is planner_plan


def test_diagnostic_requires_a_source() -> None:
    with pytest.raises(ValidationError):
        _CloudSearchTestRequest(query="filename.pdf", sources=[])


@pytest.mark.asyncio
async def test_exact_route_bypasses_planner_and_passes_literal_plan(
    monkeypatch,
) -> None:
    body = _CloudSearchTestRequest(
        query="QA PDF Fixture.pdf", sources=["onedrive"], exact_query=True
    )
    received: list[dict] = []

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("exact diagnostics must not call the planner")

    async def noop(*_args, **_kwargs):
        return None

    class _Search:
        async def search(self, _db, plan, _tenant_id):
            received.append(plan)
            return []

    monkeypatch.setattr(
        cloud_admin,
        "_require_admin",
        lambda *_args: _async_value(
            SimpleNamespace(tenant_id="tenant-1", privacy_mode=False)
        ),
    )
    monkeypatch.setattr(cloud_admin, "set_tenant_context", noop)
    monkeypatch.setattr(cloud_admin, "_get_planner", fail_if_called)
    monkeypatch.setattr(cloud_admin, "_get_cloud_search", lambda: _Search())

    await cloud_admin.cloud_search_test(body, object(), object())

    assert received == [
        {
            "should_search": True,
            "sources": ["onedrive"],
            "keywords": ["QA PDF Fixture.pdf"],
            "date_after": "",
            "max_hits": 10,
            "exact_query": True,
        }
    ]


@pytest.mark.asyncio
async def test_normal_route_uses_planner_keywords_and_selected_sources(
    monkeypatch,
) -> None:
    body = _CloudSearchTestRequest(query="renewal discussion", sources=["outlook"])
    received: list[dict] = []
    planner_calls: list[dict] = []

    async def planner_plan(**kwargs):
        planner_calls.append(kwargs)
        return {"should_search": True, "sources": ["gmail"], "keywords": ["renewal"]}

    class _Planner:
        plan = staticmethod(planner_plan)

    class _Search:
        async def search(self, _db, plan, _tenant_id):
            received.append(plan)
            return []

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        cloud_admin,
        "_require_admin",
        lambda *_args: _async_value(
            SimpleNamespace(tenant_id="tenant-1", privacy_mode=False)
        ),
    )
    monkeypatch.setattr(cloud_admin, "set_tenant_context", noop)
    monkeypatch.setattr(cloud_admin, "_get_planner", lambda: _Planner())
    monkeypatch.setattr(cloud_admin, "_get_cloud_search", lambda: _Search())

    await cloud_admin.cloud_search_test(body, object(), object())

    assert planner_calls
    assert received == [
        {
            "should_search": True,
            "sources": ["outlook"],
            "keywords": ["renewal"],
            "max_hits": 10,
        }
    ]


@pytest.mark.asyncio
async def test_no_search_plan_returns_without_provider_call(monkeypatch) -> None:
    body = _CloudSearchTestRequest(query="general question", sources=["outlook"])

    async def noop(*_args, **_kwargs):
        return None

    class _Planner:
        async def plan(self, **_kwargs):
            return {"should_search": False, "sources": [], "keywords": []}

    def fail_if_called():
        raise AssertionError("provider search should not run for a no-search plan")

    monkeypatch.setattr(
        cloud_admin,
        "_require_admin",
        lambda *_args: _async_value(
            SimpleNamespace(tenant_id="tenant-1", privacy_mode=False)
        ),
    )
    monkeypatch.setattr(cloud_admin, "set_tenant_context", noop)
    monkeypatch.setattr(cloud_admin, "_get_planner", lambda: _Planner())
    monkeypatch.setattr(cloud_admin, "_get_cloud_search", fail_if_called)

    result = await cloud_admin.cloud_search_test(body, object(), object())

    assert result.total_hits == 0
    assert result.plan["should_search"] is False


async def _async_value(value):
    return value
