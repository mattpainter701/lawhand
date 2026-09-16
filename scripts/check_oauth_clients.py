#!/usr/bin/env python3
"""Probe the Google and Microsoft OAuth clients for liveness; emit safe JSON."""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
MICROSOFT_TOKEN_TEMPLATE = (
    "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
)

# A refresh token that cannot be valid. Google authenticates the confidential
# client before it evaluates the grant, so a sentinel rejected as invalid_grant
# proves the client id and secret were themselves accepted.
GOOGLE_SENTINEL_REFRESH_TOKEN = "lawhand-ci-liveness-probe-not-a-real-token"

GUID = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
AADSTS = re.compile(r"AADSTS(\d+)")

# Entra reports a rejected or expired client secret under these codes. They are
# the alert: sign-in and every Graph integration are already failing.
ENTRA_CREDENTIAL_CODES = frozenset({"7000215", "7000216", "7000222"})
# The registration or the directory itself is gone.
ENTRA_MISSING_CODES = frozenset({"700016", "90002", "900023"})
# Access blocked before any credential verdict was reached.
ENTRA_BLOCKED_CODES = frozenset({"53003"})

# Google returns these only when the client itself was refused.
GOOGLE_CREDENTIAL_ERRORS = frozenset({"invalid_client", "unauthorized_client"})

PASSING = frozenset({"passed", "passed_client_authenticated", "not_configured"})


class TransportError(Exception):
    """The provider was never reached cleanly, so there is no credential verdict."""


def classify_google(status, payload):
    """Map one Google token response to an outcome. Pure; no network."""
    if not isinstance(payload, dict):
        return "unclassified"
    error = payload.get("error")
    # The sentinel refresh token is the only thing that should have been
    # refused. Reaching this means the client id and secret were accepted.
    if status == 400 and error == "invalid_grant":
        return "passed"
    if error in GOOGLE_CREDENTIAL_ERRORS:
        return "credential_rejected"
    # Includes a 200, which a sentinel token must never produce.
    return "unclassified"


def classify_microsoft(status, payload):
    """Map one Entra token response to an outcome. Pure; no network."""
    if not isinstance(payload, dict):
        return "unclassified"
    if status == 200:
        return "passed" if payload.get("access_token") else "unclassified"
    # Entra's OAuth `error` field is not a reliable discriminator: an absent
    # application surfaces as unauthorized_client and a pseudo-tenant block as
    # invalid_grant. Only the AADSTS code is stable, so classify on that.
    match = AADSTS.search(str(payload.get("error_description", "")))
    if match is None:
        return "unclassified"
    code = match.group(1)
    if code in ENTRA_CREDENTIAL_CODES:
        return "credential_rejected"
    if code in ENTRA_MISSING_CODES:
        return "app_not_found"
    if code in ENTRA_BLOCKED_CODES:
        return "probe_blocked"
    # Entra authenticates a confidential client before it evaluates scopes and
    # roles, so any other clean rejection still proves the secret is live. A
    # `.default` request by an app holding no application permissions lands
    # here, and that is a permissions question, not a dead key.
    return "passed_client_authenticated"


def _read_json(response):
    try:
        body = response.read(65536)
    except OSError:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def post_form(url, fields, *, timeout=15, attempts=3, sleep=time.sleep):
    """POST a form and return (status, payload).

    A clean 4xx is returned for classification. Anything that leaves the
    credentials unjudged - a timeout, a socket error, a 5xx - is retried and
    then raised, so provider flakiness is never reported as a dead key.
    """
    body = urllib.parse.urlencode(fields).encode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "LawHand-oauth-client-check/1.0",
        "Accept": "application/json",
    }
    reason = "unknown"
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, _read_json(response)
        except urllib.error.HTTPError as exc:
            payload = _read_json(exc)
            exc.close()
            if exc.code < 500:
                return exc.code, payload
            reason = f"http_{exc.code}"
        except TimeoutError:
            reason = "timeout"
        except (OSError, ValueError) as exc:
            reason = type(exc).__name__
        if attempt + 1 < attempts:
            sleep(2**attempt)
    raise TransportError(reason)


def probe_google(client_id, client_secret, **kwargs):
    if not client_id or not client_secret:
        return {"outcome": "not_configured"}
    fields = {
        "grant_type": "refresh_token",
        "refresh_token": GOOGLE_SENTINEL_REFRESH_TOKEN,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    try:
        status, payload = post_form(GOOGLE_TOKEN_URL, fields, **kwargs)
    except TransportError as exc:
        return {"outcome": "transport_error", "detail": str(exc)}
    result = {"outcome": classify_google(status, payload), "http_status": status}
    if isinstance(payload, dict) and payload.get("error"):
        # The short error enum only. error_description can echo the client id.
        result["provider_error"] = str(payload["error"])[:64]
    return result


def probe_microsoft(client_id, client_secret, home_tenant_id, **kwargs):
    if not client_id or not client_secret:
        return {"outcome": "not_configured"}
    if not GUID.match(home_tenant_id or ""):
        # client_credentials needs the directory the registration lives in.
        # MICROSOFT_TENANT_ID is `organizations` by design and cannot be used.
        return {
            "outcome": "probe_blocked",
            "detail": "home_tenant_id_missing_or_invalid",
        }
    fields = {
        "grant_type": "client_credentials",
        "scope": "https://graph.microsoft.com/.default",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    url = MICROSOFT_TOKEN_TEMPLATE.format(tenant=home_tenant_id)
    try:
        status, payload = post_form(url, fields, **kwargs)
    except TransportError as exc:
        return {"outcome": "transport_error", "detail": str(exc)}
    result = {"outcome": classify_microsoft(status, payload), "http_status": status}
    if isinstance(payload, dict):
        # The AADSTS number only. The description quotes the client id.
        match = AADSTS.search(str(payload.get("error_description", "")))
        if match:
            result["provider_error"] = f"AADSTS{match.group(1)}"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider", choices=("google", "microsoft", "all"), default="all"
    )
    args = parser.parse_args()

    results = {}
    if args.provider in ("google", "all"):
        results["google"] = probe_google(
            os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        )
    if args.provider in ("microsoft", "all"):
        results["microsoft"] = probe_microsoft(
            os.getenv("MICROSOFT_CLIENT_ID", "").strip(),
            os.getenv("MICROSOFT_CLIENT_SECRET", "").strip(),
            os.getenv("MICROSOFT_ENTRA_HOME_TENANT_ID", "").strip(),
        )

    passed = all(result["outcome"] in PASSING for result in results.values())
    print(json.dumps(dict(schema_version=1, passed=passed, results=results), indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
