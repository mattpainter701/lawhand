"""The published scope matrix must equal the scopes the app actually requests.

The public /requirements page tells a Microsoft 365 or Google Workspace
administrator exactly what consent they are about to grant. That page reads
frontend/src/marketing/integration-scopes.json, which cannot import these constants, so
this test is the only thing standing between a narrowed scope and a stale
public claim.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.routers.integrations import (
    GOOGLE_ADMIN_SCOPES,
    GOOGLE_USER_SCOPES,
    MICROSOFT_USER_SCOPES,
    _admin_request_scopes,
    GOOGLE_SOLO_SCOPES,
    _google_account_mode_matches,
    _google_scopes_for_mode,
)
from app.services.teams import TEAMS_CONNECT_SCOPES

SCOPE_FILE = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "marketing"
    / "integration-scopes.json"
)


def _published() -> dict:
    return json.loads(SCOPE_FILE.read_text())["providers"]


@pytest.mark.parametrize(
    ("provider", "intent", "actual"),
    [
        # The admin consent also carries the OpenID Connect sign-in scopes.
        ("microsoft", "admin", _admin_request_scopes(False)),
        ("microsoft", "user", MICROSOFT_USER_SCOPES),
        ("microsoft", "teamsOptIn", TEAMS_CONNECT_SCOPES),
        ("google", "admin", GOOGLE_ADMIN_SCOPES),
        ("google", "user", GOOGLE_USER_SCOPES),
    ],
)
def test_published_scopes_match_requested_scopes(
    provider: str, intent: str, actual: str
) -> None:
    published = _published()[provider][intent]
    # Order is a presentation choice on the marketing page; membership is not.
    assert sorted(published) == sorted(actual.split()), (
        f"frontend/src/marketing/integration-scopes.json publishes {provider}.{intent} scopes "
        "that no longer match the consent request. Update the JSON and the "
        "/requirements page copy together."
    )


def test_no_provider_publishes_an_undeclared_intent() -> None:
    for provider, intents in _published().items():
        assert set(intents) <= {
            "admin",
            "user",
            "teamsOptIn",
        }, f"{provider} declares an intent the public page does not render"


def test_personal_google_onboarding_scopes_are_least_privilege() -> None:
    assert (
        "https://www.googleapis.com/auth/admin.directory.user.readonly"
        not in GOOGLE_SOLO_SCOPES
    )
    assert "https://www.googleapis.com/auth/gmail.readonly" in GOOGLE_SOLO_SCOPES
    assert "https://www.googleapis.com/auth/drive" in GOOGLE_SOLO_SCOPES
    assert "https://www.googleapis.com/auth/calendar" in GOOGLE_SOLO_SCOPES


def test_google_onboarding_mode_selects_exact_scope_bundle() -> None:
    assert _google_scopes_for_mode("admin", "personal") == GOOGLE_SOLO_SCOPES
    assert _google_scopes_for_mode("admin", "workspace") == GOOGLE_ADMIN_SCOPES
    assert "admin.directory.user.readonly" in _google_scopes_for_mode(
        "admin", "workspace"
    )
    assert "admin.directory.user.readonly" not in _google_scopes_for_mode(
        "admin", "personal"
    )


def test_google_onboarding_mode_requires_matching_verified_account_tier() -> None:
    assert _google_account_mode_matches("personal", "personal") is True
    assert _google_account_mode_matches("workspace", "workspace") is True
    assert _google_account_mode_matches("personal", "workspace") is False
    assert _google_account_mode_matches("workspace", "personal") is False
