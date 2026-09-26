"""The published scope matrix must equal the scopes the app actually requests.

The public /requirements page tells a Microsoft 365 or Google Workspace
administrator exactly what consent they are about to grant. That page reads
frontend/src/marketing/integration-scopes.json, which cannot import these constants, so
this test is the only thing standing between a narrowed scope and a stale
public claim.
"""

from __future__ import annotations

import json
import re
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
from app.routers.auth import MICROSOFT_SIGN_IN_SCOPE
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


ADMIN_GUIDE = SCOPE_FILE.parents[2] / "platform_docs" / "administrative-guide"
DATA_VISIBILITY_GUIDE = ADMIN_GUIDE / "16-integration-data-visibility.md"
TEAMS_GUIDE = ADMIN_GUIDE / "13-microsoft-teams-administration.md"
# A backticked Microsoft Graph permission name, e.g. `Files.Read.All`.
GRAPH_PERMISSION = re.compile(r"`([A-Z][A-Za-z]+(?:\.[A-Za-z]+)+)`")


def _backticked(path: Path) -> set[str]:
    return set(re.findall(r"`([^`]+)`", path.read_text()))


def _google_short_name(scope: str) -> str:
    return scope.rsplit("/auth/", 1)[-1]


def test_admin_guide_names_every_scope_the_app_requests() -> None:
    """The data-visibility chapter is the firm's consent disclosure.

    It once omitted Mail.Send and gmail.send and called Gmail read-only (D81),
    so every requested scope must appear in it, in backticks, by name.
    """
    named = _backticked(DATA_VISIBILITY_GUIDE)
    microsoft = {
        *_admin_request_scopes(False).split(),
        *MICROSOFT_USER_SCOPES.split(),
        *TEAMS_CONNECT_SCOPES.split(),
        *MICROSOFT_SIGN_IN_SCOPE.split(),
    }
    google = {
        _google_short_name(scope)
        for scopes in (GOOGLE_ADMIN_SCOPES, GOOGLE_USER_SCOPES, GOOGLE_SOLO_SCOPES)
        for scope in scopes.split()
    }
    assert sorted((microsoft | google) - named) == []


def test_admin_guides_name_no_graph_permission_the_app_does_not_request() -> None:
    requested = {
        *_admin_request_scopes(True).split(),
        *MICROSOFT_USER_SCOPES.split(),
        *MICROSOFT_SIGN_IN_SCOPE.split(),
    }
    # Voice capture is a separate application-only credential (teams_voice).
    allowed = {"CallRecords.Read.All"}
    for guide in (DATA_VISIBILITY_GUIDE, TEAMS_GUIDE):
        named = set(GRAPH_PERMISSION.findall(guide.read_text()))
        assert sorted(named - requested - allowed) == [], guide.name
    assert set(TEAMS_CONNECT_SCOPES.split()) <= _backticked(TEAMS_GUIDE)


def test_personal_google_scopes_are_workspace_scopes_without_the_directory() -> None:
    # The onboarding wizard derives the personal-account list this way from the
    # published Workspace matrix (frontend integrationScopeLabels.js).
    directory = "https://www.googleapis.com/auth/admin.directory.user.readonly"
    assert set(GOOGLE_SOLO_SCOPES.split()) == set(GOOGLE_ADMIN_SCOPES.split()) - {
        directory
    }


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
