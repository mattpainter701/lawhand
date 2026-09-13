"""A successful re-authorization must clear stale refresh-failure state.

Every callback upsert path used to set ``is_active = True`` and stop, leaving
``health="revoked"``, the old ``last_refresh_error`` and ``last_refresh_at`` in
place. ``apply_scope_audit`` then refused to lift ``revoked`` (correctly, for a
refresh cycle), so a successful re-auth still rendered as "Reconnect Required"
beside a weeks-old ``invalid_grant``. These tests pin the fix at the callback
helper and pin the refresh-path guard that must not regress.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routers import integrations
from app.routers.integrations import (
    GOOGLE_ADMIN_SCOPES,
    GOOGLE_USER_SCOPES,
    MICROSOFT_USER_SCOPES,
    _admin_scopes,
    _record_fresh_grant,
    _scope_is_granted,
)
from app.services.integration_observability import (
    apply_scope_audit,
    clear_refresh_failure,
    summarize_user_tokens,
)
from app.services.token_vault import _record_refresh_failure

STALE_ERROR = "400 invalid_grant Token has been expired or revoked."
STALE_AT = datetime.now(timezone.utc) - timedelta(days=62)


@pytest.fixture(autouse=True)
def _plain_tokens(monkeypatch):
    monkeypatch.setattr(integrations, "encrypt_token", lambda value: f"enc:{value}")


def _revoked_row(**extra):
    return SimpleNamespace(
        encrypted_access_token="enc:old",
        encrypted_refresh_token="enc:old-refresh",
        token_expires_at=STALE_AT,
        scopes="",
        missing_scopes=None,
        health="revoked",
        is_active=False,
        last_refresh_error=STALE_ERROR,
        last_refresh_at=STALE_AT,
        **extra,
    )


def _grant(row, scope_str):
    _record_fresh_grant(
        row,
        access_token="new-access",
        refresh_token="new-refresh",
        expires_in=3600,
        scope_str=scope_str,
    )


@pytest.mark.parametrize(
    ("provider", "required"),
    [
        ("google", GOOGLE_ADMIN_SCOPES),
        ("google", GOOGLE_USER_SCOPES),
        ("microsoft", _admin_scopes(False)),
        ("microsoft", MICROSOFT_USER_SCOPES),
    ],
    ids=["google-admin", "google-user", "microsoft-admin", "microsoft-user"],
)
def test_fresh_full_scope_grant_clears_revoked_health(provider, required):
    row = _revoked_row()

    _grant(row, required)
    missing = apply_scope_audit(row, provider, required, _scope_is_granted)

    assert missing == []
    assert row.health == "healthy"
    assert row.is_active is True
    assert row.last_refresh_error is None
    assert row.last_refresh_at > STALE_AT
    assert row.encrypted_access_token == "enc:new-access"
    assert row.encrypted_refresh_token == "enc:new-refresh"
    assert row.token_expires_at > datetime.now(timezone.utc)


def test_fresh_grant_with_a_real_scope_gap_still_reports_missing_scopes():
    """Clearing the stale failure must not hide a genuine consent gap."""
    row = _revoked_row()
    partial = " ".join(GOOGLE_ADMIN_SCOPES.split()[:-1])

    _grant(row, partial)
    missing = apply_scope_audit(row, "google", GOOGLE_ADMIN_SCOPES, _scope_is_granted)

    assert missing == [GOOGLE_ADMIN_SCOPES.split()[-1]]
    assert row.health == "missing_scopes"
    assert row.is_active is True
    assert row.last_refresh_error is None


def test_fresh_grant_without_refresh_token_stores_no_refresh_token():
    row = _revoked_row()

    _record_fresh_grant(
        row,
        access_token="new-access",
        refresh_token=None,
        expires_in=60,
        scope_str=GOOGLE_USER_SCOPES,
    )

    assert row.encrypted_refresh_token is None
    assert row.health == "healthy"


def test_invalid_grant_on_refresh_still_revokes_and_deactivates():
    """The refresh path guard is the reason the fix lives at the callback."""
    row = SimpleNamespace(
        health="healthy",
        is_active=True,
        last_refresh_error=None,
        last_refresh_at=None,
        scopes=GOOGLE_ADMIN_SCOPES,
        missing_scopes=None,
    )

    _record_refresh_failure(row, 400, '{"error": "invalid_grant"}')
    apply_scope_audit(row, "google", GOOGLE_ADMIN_SCOPES, _scope_is_granted)

    assert row.health == "revoked"
    assert row.is_active is False
    assert row.last_refresh_error.startswith("400 ")
    assert row.last_refresh_at is not None


def test_clear_refresh_failure_tolerates_rows_without_health_columns():
    row = SimpleNamespace(scopes="x")

    clear_refresh_failure(row)

    assert row.scopes == "x"


def test_summarize_user_tokens_splits_healthy_from_reauth_by_provider():
    rows = [
        SimpleNamespace(provider="google", health="healthy"),
        SimpleNamespace(provider="google", health="revoked"),
        SimpleNamespace(provider="google", health="refresh_failed"),
        SimpleNamespace(provider="google", health=None),
        SimpleNamespace(provider="microsoft", health="missing_scopes"),
    ]

    assert summarize_user_tokens(rows, "google") == {
        "total": 4,
        "healthy": 2,
        "needs_reauth": 2,
    }
    assert summarize_user_tokens(rows, "microsoft") == {
        "total": 1,
        "healthy": 0,
        "needs_reauth": 1,
    }
    assert summarize_user_tokens([], "google") == {
        "total": 0,
        "healthy": 0,
        "needs_reauth": 0,
    }
