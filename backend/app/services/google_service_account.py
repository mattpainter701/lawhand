"""Google service-account auth for org-owned workspace storage.

Delegated OAuth tokens belong to the admin who completed the consent flow, so
they stop working the moment that person is deactivated, renamed, or deleted.
A service account is owned by the Google Cloud project, not a human, so the
firm's document root keeps working through staff turnover.

Two modes are supported:

* Plain service-account access — the account is added as a member of an
  org-owned Shared Drive and mints its own tokens. This is the storage path.
* Domain-wide delegation — set ``subject`` to a Workspace user to impersonate
  them. Used for directory and mail operations that require a user context.

The module only mints short-lived access tokens; key material stays in
``GOOGLE_SERVICE_ACCOUNT_KEY`` (inline JSON or a path).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx
from jose import jwt

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
JWT_BEARER_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
# Least privilege for the document root: files it creates and manages in the
# Shared Drive. Directory and Gmail scopes are separate and only requested by
# callers that need them.
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

# Access tokens are valid for ~1h; refresh a little early.
_TOKEN_REFRESH_SKEW_SECONDS = 60

_token_cache: dict[str, tuple[str, float]] = {}


def load_service_account() -> dict | None:
    """Return the parsed service-account key, or None when not configured."""
    raw = (settings.GOOGLE_SERVICE_ACCOUNT_KEY or "").strip()
    if not raw:
        return None
    try:
        if raw.lstrip().startswith("{"):
            data = json.loads(raw)
        else:
            path = Path(raw)
            if not path.exists():
                logger.warning("GOOGLE_SERVICE_ACCOUNT_KEY path was not found")
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        logger.warning("GOOGLE_SERVICE_ACCOUNT_KEY could not be parsed: %s", exc)
        return None
    if not data.get("client_email") or not data.get("private_key"):
        logger.warning(
            "Google service-account key is missing client_email or private_key"
        )
        return None
    return data


def is_configured() -> bool:
    return load_service_account() is not None


def service_account_email() -> str | None:
    account = load_service_account()
    if account:
        return account.get("client_email")
    return (settings.GOOGLE_SERVICE_ACCOUNT_EMAIL or "").strip() or None


def _cache_key(scopes: list[str], subject: str | None) -> str:
    return f"{subject or 'service-account'}::{' '.join(sorted(scopes))}"


def _clear_cache() -> None:
    _token_cache.clear()


def _build_assertion(
    account: dict, scopes: list[str], subject: str | None, issued_at: int
) -> str:
    payload = {
        "iss": account["client_email"],
        "scope": " ".join(scopes),
        "aud": GOOGLE_TOKEN_URL,
        "iat": issued_at,
        "exp": issued_at + 3600,
    }
    if subject:
        payload["sub"] = subject
    return jwt.encode(payload, account["private_key"], algorithm="RS256")


async def get_access_token(
    scopes: list[str] | None = None,
    *,
    subject: str | None = None,
) -> str | None:
    """Mint (and cache) a service-account access token.

    Returns None when the service account is not configured or the provider
    rejects the assertion. Never raises on a missing credential so callers can
    fall back or surface a clear "not configured" state.
    """
    account = load_service_account()
    if not account:
        return None
    resolved_scopes = list(scopes or DRIVE_SCOPES)
    key = _cache_key(resolved_scopes, subject)
    now = time.time()
    cached = _token_cache.get(key)
    if cached and cached[1] > now + _TOKEN_REFRESH_SKEW_SECONDS:
        return cached[0]

    assertion = _build_assertion(account, resolved_scopes, subject, int(now))
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": JWT_BEARER_GRANT,
                    "assertion": assertion,
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("Google service-account token request failed: %s", exc)
        return None

    if resp.status_code != 200:
        logger.warning(
            "Google service-account token rejected: status=%d body=%s",
            resp.status_code,
            resp.text[:300],
        )
        return None

    data = resp.json()
    token = data.get("access_token")
    if not token:
        logger.warning("Google service-account token response had no access_token")
        return None
    expires_in = int(data.get("expires_in", 3600))
    _token_cache[key] = (token, now + expires_in)
    return token
