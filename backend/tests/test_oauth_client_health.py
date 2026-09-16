"""Offline regressions for the Google/Microsoft OAuth client liveness probe.

Every provider response here was observed against the real token endpoints, so
the classifier is pinned to what the providers actually return rather than to
what their documentation implies.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


clients = load("check_oauth_clients")

SECRET = "Q8x8Q~ops0123456789abcdefghijklmnopqrstu"
TENANT = "6babcaad-604b-40ac-a9d7-9fd97c0b779f"
CLIENT = "11111111-2222-3333-4444-555555555555"


def aadsts(code, error="invalid_client"):
    return {
        "error": error,
        "error_description": f"AADSTS{code}: Something the description explains. Trace ID: x",
    }


# ── Google ───────────────────────────────────────────────────────────────────


def test_google_sentinel_rejection_proves_the_client_authenticated():
    """Only the sentinel refresh token was refused, so the pair is live."""

    assert clients.classify_google(400, {"error": "invalid_grant"}) == "passed"


@pytest.mark.parametrize(
    "status,error", [(401, "invalid_client"), (400, "unauthorized_client")]
)
def test_google_client_refusal_is_the_alert(status, error):
    assert clients.classify_google(status, {"error": error}) == "credential_rejected"


@pytest.mark.parametrize(
    "status,payload",
    [
        (200, {"access_token": "surprise"}),  # a sentinel token must never mint one
        (400, {"error": "invalid_request"}),
        (400, None),
        (400, "not json at all"),
    ],
)
def test_google_unrecognised_responses_fail_loudly(status, payload):
    assert clients.classify_google(status, payload) == "unclassified"


# ── Microsoft ────────────────────────────────────────────────────────────────


def test_microsoft_issued_token_passes():
    assert clients.classify_microsoft(200, {"access_token": "t"}) == "passed"


def test_microsoft_200_without_a_token_is_not_a_pass():
    assert clients.classify_microsoft(200, {"token_type": "Bearer"}) == "unclassified"


@pytest.mark.parametrize("code", ["7000215", "7000216", "7000222"])
def test_microsoft_rejected_or_expired_secret_is_the_alert(code):
    """AADSTS7000222 is the expiring-secret case this whole check exists for."""

    assert clients.classify_microsoft(401, aadsts(code)) == "credential_rejected"


@pytest.mark.parametrize("code", ["700016", "90002", "900023"])
def test_microsoft_missing_registration_is_reported_separately(code):
    assert clients.classify_microsoft(400, aadsts(code)) == "app_not_found"


def test_microsoft_conditional_access_block_reaches_no_verdict():
    """Aiming the probe at /organizations or /common lands here, not on a verdict."""

    assert (
        clients.classify_microsoft(400, aadsts("53003", "invalid_grant"))
        == "probe_blocked"
    )


def test_microsoft_authorization_complaint_still_proves_the_secret_is_live():
    """Entra authenticates the client before it evaluates scopes and roles."""

    assert (
        clients.classify_microsoft(400, aadsts("65001"))
        == "passed_client_authenticated"
    )


def test_microsoft_response_without_an_aadsts_code_fails_loudly():
    assert (
        clients.classify_microsoft(400, {"error": "invalid_client"}) == "unclassified"
    )


def test_microsoft_classifies_on_the_aadsts_code_not_the_oauth_error_field():
    """Both pairs below are real. The `error` field alone would conflate them."""

    missing = {
        "error": "unauthorized_client",
        "error_description": f"AADSTS700016: Application with identifier '{CLIENT}' was not found",
    }
    blocked = {
        "error": "invalid_grant",
        "error_description": "AADSTS53003: Access has been blocked by Conditional Access policies.",
    }
    assert clients.classify_microsoft(400, missing) == "app_not_found"
    assert clients.classify_microsoft(400, blocked) == "probe_blocked"


# ── Probe wiring ─────────────────────────────────────────────────────────────


def test_absent_credentials_skip_rather_than_fail():
    assert clients.probe_google("", "")["outcome"] == "not_configured"
    assert clients.probe_microsoft("", "", TENANT)["outcome"] == "not_configured"


def test_microsoft_refuses_to_probe_without_a_home_tenant_guid(monkeypatch):
    """client_credentials cannot run against `organizations`; never guess a URL."""

    def unreachable(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("no request may be made without a valid home tenant")

    monkeypatch.setattr(clients, "post_form", unreachable)
    for tenant in ("", "organizations", "common", "not-a-guid"):
        result = clients.probe_microsoft(CLIENT, SECRET, tenant)
        assert result["outcome"] == "probe_blocked"
        assert result["detail"] == "home_tenant_id_missing_or_invalid"


def test_transport_failure_is_not_reported_as_a_dead_key(monkeypatch):
    def unreachable(*args, **kwargs):
        raise clients.TransportError("timeout")

    monkeypatch.setattr(clients, "post_form", unreachable)
    assert clients.probe_google(CLIENT, SECRET)["outcome"] == "transport_error"
    assert (
        clients.probe_microsoft(CLIENT, SECRET, TENANT)["outcome"] == "transport_error"
    )


def test_server_errors_are_retried_then_raised(monkeypatch):
    attempts = []

    def failing(request, timeout=None):
        attempts.append(request.full_url)
        raise OSError("connection reset")

    monkeypatch.setattr(clients.urllib.request, "urlopen", failing)
    with pytest.raises(clients.TransportError):
        clients.post_form(
            "https://example.invalid/token", {"a": "b"}, sleep=lambda _: None
        )
    assert len(attempts) == 3


def test_a_clean_4xx_is_classified_rather_than_retried(monkeypatch):
    calls = []

    def rejecting(request, timeout=None):
        calls.append(request.full_url)
        raise clients.urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {}, None
        )

    monkeypatch.setattr(clients.urllib.request, "urlopen", rejecting)
    status, payload = clients.post_form("https://example.invalid/token", {"a": "b"})
    assert status == 401 and payload is None
    assert len(calls) == 1


# ── Output safety ────────────────────────────────────────────────────────────


def test_emitted_json_never_carries_the_secret(monkeypatch, capsys):
    """The failure path is where a secret would leak; assert it does not."""

    description = (
        f"AADSTS7000215: Invalid client secret provided for '{CLIENT}'. Trace ID: x"
    )
    monkeypatch.setattr(
        clients,
        "post_form",
        lambda *a, **k: (
            401,
            {"error": "invalid_client", "error_description": description},
        ),
    )
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", CLIENT)
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("MICROSOFT_ENTRA_HOME_TENANT_ID", TENANT)

    monkeypatch.setattr(
        "sys.argv", ["check_oauth_clients.py", "--provider", "microsoft"]
    )
    assert clients.main() == 1

    output = capsys.readouterr().out
    assert SECRET not in output
    # The full description quotes the client id; only the code may be reported.
    assert "Invalid client secret provided" not in output
    payload = json.loads(output)
    assert payload["passed"] is False
    assert payload["results"]["microsoft"]["provider_error"] == "AADSTS7000215"


def test_all_providers_unconfigured_exits_clean(monkeypatch, capsys):
    for key in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "MICROSOFT_CLIENT_ID",
        "MICROSOFT_CLIENT_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("sys.argv", ["check_oauth_clients.py"])

    assert clients.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True
    assert {r["outcome"] for r in payload["results"].values()} == {"not_configured"}
