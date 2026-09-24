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
import uuid
from pathlib import Path

import httpx
from jose import jwt
from sqlalchemy import select

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


DRIVE_ACCESS_CACHE_SECONDS = 600
_DRIVE_ACCESS_CACHE: dict[tuple[str, str], float] = {}
GOOGLE_DRIVE_API = "https://www.googleapis.com/drive/v3"


def _org_shared_drive_binding(cloud_root: object) -> dict | None:
    """Return the google_drive binding when it is an org Shared Drive root."""
    if not isinstance(cloud_root, dict):
        return None
    binding = cloud_root.get("google_drive")
    if not isinstance(binding, dict):
        return None
    if (binding.get("owner_type") or "").strip() != "org_shared_drive":
        return None
    return binding


async def _load_tenant_cloud_root(db, tenant_id: object | None):
    if db is None or tenant_id is None:
        return None
    try:
        from app.models.tenant import Tenant

        result = await db.execute(
            select(Tenant.cloud_root_folder).where(
                Tenant.id == uuid.UUID(str(tenant_id))
            )
        )
        return result.scalar_one_or_none()
    except Exception:
        logger.warning("Could not read tenant cloud root", exc_info=True)
        return None


async def _service_account_can_access_drive(token: str, drive_id: str) -> bool:
    """Probe the Shared Drive with the service-account token."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{GOOGLE_DRIVE_API}/drives/{drive_id}",
                params={"fields": "id"},
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError:
        return False
    return resp.status_code == 200


def _clear_drive_access_cache() -> None:
    _DRIVE_ACCESS_CACHE.clear()


# Returned by :func:`service_account_drive_scope` when the platform service
# account token is in use but the tenant has no org Shared Drive to pin to.
NO_TENANT_DRIVE = ""


async def service_account_drive_scope(
    db,
    tenant_id: object | None,
    token: str | None,
    *,
    cloud_root: object | None = None,
) -> str | None:
    """Pin Drive listings made with the platform service account to one tenant.

    One service account is a member of every tenant's org Shared Drive, so a
    ``corpora=allDrives`` search or an ``includeItemsFromAllDrives`` listing
    made with its token spans every customer's drive. Callers must restrict
    such requests to ``corpora=drive&driveId=<this tenant's drive>``.

    Returns ``None`` for a delegated (per-account) token, the tenant's drive id
    for the service-account token, or :data:`NO_TENANT_DRIVE` when the
    service-account token is in use without a bound drive, in which case the
    caller must not list or read anything.
    """
    if not token or not is_configured():
        return None
    service_token = await get_access_token(DRIVE_SCOPES)
    if not service_token or token != service_token:
        return None
    if cloud_root is None:
        cloud_root = await _load_tenant_cloud_root(db, tenant_id)
    binding = _org_shared_drive_binding(cloud_root) or {}
    return str(binding.get("drive_id") or "").strip() or NO_TENANT_DRIVE


async def prefer_service_account(
    db,
    tenant_id: object | None,
    delegated: str | None,
    *,
    cloud_root: object | None = None,
):
    """Prefer the service-account token for an org Shared Drive tenant.

    Root creation is not enough on its own: matter-folder provisioning,
    uploads, reads, search, sharing, rename, and repair must all use an
    identity that survives the connecting administrator. The service-account
    token is only returned once a probe confirms it can actually reach this
    customer's drive; otherwise the supplied delegated token is used, so a
    minted-but-unauthorized service account never breaks storage operations.
    Pass ``cloud_root`` when the caller already holds it to avoid a second
    tenant read.
    """
    if not delegated and not is_configured():
        return delegated
    if cloud_root is None:
        cloud_root = await _load_tenant_cloud_root(db, tenant_id)
    binding = _org_shared_drive_binding(cloud_root)
    if not binding:
        return delegated
    drive_id = str(binding.get("drive_id") or "").strip()
    if not drive_id:
        return delegated
    service_token = await get_access_token(DRIVE_SCOPES)
    if not service_token:
        return delegated

    cache_key = (str(tenant_id), drive_id)
    now = time.time()
    if _DRIVE_ACCESS_CACHE.get(cache_key, 0) > now:
        return service_token
    if await _service_account_can_access_drive(service_token, drive_id):
        _DRIVE_ACCESS_CACHE[cache_key] = now + DRIVE_ACCESS_CACHE_SECONDS
        return service_token
    logger.warning(
        "Service account cannot reach Google Shared Drive %s for tenant %s; "
        "using the delegated token",
        drive_id,
        tenant_id,
    )
    return delegated
