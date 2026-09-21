from __future__ import annotations

import uuid

from app.services.mcp_product import _summarize_usage_rows


def test_usage_summary_separates_billable_external_from_internal_chat() -> None:
    key_id = uuid.uuid4()
    grant_id = uuid.uuid4()
    rows = [
        (key_id, None, "product_key", 200, 3, 12),
        (None, grant_id, "research_oauth", 200, 2, 5),
        (None, None, "internal_chat", 200, 7, 20),
        (key_id, None, "product_key", 500, 1, 0),
    ]

    summary = _summarize_usage_rows(rows, days=30)

    assert summary["total_calls"] == 13
    assert summary["total_results"] == 37
    # Only successful calls made with a product key or OAuth grant are billed.
    assert summary["billable_calls"] == 5
    assert summary["unbilled_calls"] == 8
    assert summary["failed_calls"] == 1

    key_bucket = next(
        item for item in summary["by_key"] if item["product_key_id"] == str(key_id)
    )
    assert key_bucket["calls"] == 4
    assert key_bucket["billable_calls"] == 3

    auth = {item["auth_type"]: item for item in summary["by_auth"]}
    assert auth["internal_chat"]["calls"] == 7
    assert auth["internal_chat"]["billable_calls"] == 0
    assert auth["research_oauth"]["billable_calls"] == 2


def test_usage_summary_handles_no_events() -> None:
    summary = _summarize_usage_rows([], days=7)

    assert summary == {
        "days": 7,
        "total_calls": 0,
        "total_results": 0,
        "billable_calls": 0,
        "unbilled_calls": 0,
        "failed_calls": 0,
        "by_key": [],
        "by_auth": [],
    }
