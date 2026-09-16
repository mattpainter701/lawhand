"""Platform-managed Twilio sender (operator infrastructure).

Early LawHand customers send SMS through one LawHand-owned Twilio account
rather than bringing their own. The operator stores that account in the
platform settings store with the auth token encrypted by the same
``token_vault`` used for model provider keys. This is operator
infrastructure, not tenant data, so it is intentionally not tenant-scoped.

The separate, firm-owned tenant path (``app.services.sms``) is untouched.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import PlatformSetting
from app.services.token_vault import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

PLATFORM_SMS_KEY = "platform_sms_provider_v1"
PROVIDER = "twilio"
TWILIO_MESSAGES_URL = (
    "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
)
_E164 = re.compile(r"^\+[1-9]\d{1,14}$")
_TOKEN_HINT_CHARS = 4


class PlatformSmsError(RuntimeError):
    """A safe, operator-facing failure for the shared Twilio sender."""

    def __init__(
        self,
        message: str,
        status_code: int = 503,
        *,
        code: str | None = None,
        provider_status: int | None = None,
        provider_code: int | str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        # What Twilio said, when Twilio is the one who said no. Kept alongside
        # our own ``code`` so an operator can look the number up in Twilio's
        # error reference instead of guessing from prose.
        self.provider_status = provider_status
        self.provider_code = provider_code


@dataclass(frozen=True)
class PlatformSmsCredentials:
    account_sid: str
    auth_token: str
    messaging_service_sid: str | None
    from_number: str | None
    status_callback_url: str | None


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _mask_account_sid(value: str) -> str | None:
    if not value:
        return None
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:4]}…{value[-3:]}"


def _sender_ready(config: dict) -> bool:
    return bool(
        _clean(config.get("account_sid"))
        and config.get("encrypted_auth_token")
        and (
            _clean(config.get("messaging_service_sid"))
            or _clean(config.get("from_number"))
        )
    )


def _public_view(config: dict | None) -> dict:
    config = config if isinstance(config, dict) else {}
    account_sid = _clean(config.get("account_sid"))
    return {
        "provider": PROVIDER,
        "configured": bool(config),
        "account_sid": _mask_account_sid(account_sid),
        "auth_token_configured": bool(config.get("encrypted_auth_token")),
        "auth_token_hint": config.get("auth_token_hint") or "",
        "messaging_service_sid": config.get("messaging_service_sid") or None,
        "from_number": config.get("from_number") or None,
        "status_callback_url": config.get("status_callback_url") or None,
        "sender_ready": _sender_ready(config),
        "is_active": bool(config.get("is_active", False)),
        "updated_at": config.get("updated_at"),
        "updated_by": config.get("updated_by"),
    }


async def get_platform_sms_config(db: AsyncSession) -> dict | None:
    row = await db.scalar(
        select(PlatformSetting).where(PlatformSetting.key == PLATFORM_SMS_KEY)
    )
    value = row.value if row else None
    return value if isinstance(value, dict) else None


async def get_platform_sms_provider_public(db: AsyncSession) -> dict:
    return _public_view(await get_platform_sms_config(db))


async def upsert_platform_sms_provider(
    db: AsyncSession,
    *,
    account_sid: str | None = None,
    auth_token: str | None = None,
    messaging_service_sid: str | None = None,
    from_number: str | None = None,
    status_callback_url: str | None = None,
    is_active: bool | None = None,
    actor: str | None = None,
) -> dict:
    """Create or update the shared Twilio account.

    Only non-None fields are written. ``auth_token`` is re-encrypted when
    supplied and otherwise left untouched, so the operator can edit the sender
    without re-entering the secret.
    """

    row = await db.scalar(
        select(PlatformSetting).where(PlatformSetting.key == PLATFORM_SMS_KEY)
    )
    config = dict(row.value) if row and isinstance(row.value, dict) else {}

    if account_sid is not None:
        config["account_sid"] = _clean(account_sid)
    if messaging_service_sid is not None:
        config["messaging_service_sid"] = _clean(messaging_service_sid)
    if from_number is not None:
        config["from_number"] = _clean(from_number)
    if status_callback_url is not None:
        config["status_callback_url"] = _clean(status_callback_url)
    if is_active is not None:
        config["is_active"] = bool(is_active)

    if auth_token is not None and _clean(auth_token):
        token = _clean(auth_token)
        config["encrypted_auth_token"] = encrypt_token(token)
        config["auth_token_hint"] = token[-_TOKEN_HINT_CHARS:]

    if auth_token is not None and not _clean(auth_token):
        # Explicitly blanking the field clears the stored secret.
        config.pop("encrypted_auth_token", None)
        config.pop("auth_token_hint", None)

    # Validate shape before completeness: "your Messaging Service SID is
    # actually a Verify SID" is a far more useful answer than "something is
    # missing", and it is the mistake that reaches Twilio and comes back as a
    # 502 nobody can act on.
    _validate_sid(
        _clean(config.get("account_sid")),
        field="account_sid",
        expected_prefix="AC",
        label="Account SID",
    )
    _validate_sid(
        _clean(config.get("messaging_service_sid")),
        field="messaging_service_sid",
        expected_prefix="MG",
        label="Messaging Service SID",
    )
    _validate_sender_number(_clean(config.get("from_number")))

    if not (_clean(config.get("account_sid")) and config.get("encrypted_auth_token")):
        raise PlatformSmsError(
            "Account SID and Auth Token are both required.",
            status_code=400,
            code="platform_sms_incomplete",
        )
    if not (
        _clean(config.get("messaging_service_sid")) or _clean(config.get("from_number"))
    ):
        raise PlatformSmsError(
            "A Messaging Service SID or a From number is required.",
            status_code=400,
            code="platform_sms_incomplete",
        )

    config["provider"] = PROVIDER
    config.setdefault("is_active", True)
    config["updated_at"] = datetime.now(timezone.utc).isoformat()
    config["updated_by"] = actor

    if row is None:
        row = PlatformSetting(key=PLATFORM_SMS_KEY, value=config)
        db.add(row)
    else:
        row.value = config
    await db.commit()
    await db.refresh(row)
    return dict(row.value)


async def delete_platform_sms_provider(db: AsyncSession) -> bool:
    row = await db.scalar(
        select(PlatformSetting).where(PlatformSetting.key == PLATFORM_SMS_KEY)
    )
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def resolve_platform_sms_credentials(
    db: AsyncSession,
) -> PlatformSmsCredentials:
    config = await get_platform_sms_config(db)
    if not config or not config.get("is_active") or not _sender_ready(config):
        raise PlatformSmsError(
            "The shared SMS sender is not configured or is inactive.",
            status_code=503,
            code="platform_sms_unconfigured",
        )
    try:
        token = decrypt_token(config["encrypted_auth_token"]).strip()
    except Exception as exc:  # noqa: BLE001 - never leak provider detail
        raise PlatformSmsError(
            "The shared SMS credentials are unavailable.",
            status_code=503,
            code="platform_sms_credentials_unavailable",
        ) from exc
    if not token:
        raise PlatformSmsError(
            "The shared SMS credentials are unavailable.",
            status_code=503,
            code="platform_sms_credentials_unavailable",
        )
    # A sender stored before these checks existed is still wrong; catching it
    # here means the operator is told which field to fix instead of watching a
    # send fail at Twilio.
    _validate_sid(
        _clean(config.get("account_sid")),
        field="account_sid",
        expected_prefix="AC",
        label="stored Account SID",
    )
    _validate_sid(
        _clean(config.get("messaging_service_sid")),
        field="messaging_service_sid",
        expected_prefix="MG",
        label="stored Messaging Service SID",
    )
    _validate_sender_number(_clean(config.get("from_number")))

    return PlatformSmsCredentials(
        account_sid=_clean(config.get("account_sid")),
        auth_token=token,
        messaging_service_sid=_clean(config.get("messaging_service_sid")) or None,
        from_number=_clean(config.get("from_number")) or None,
        status_callback_url=_clean(config.get("status_callback_url")) or None,
    )


# Twilio resource SIDs are a two-letter type prefix and 32 hex characters. The
# prefix is the part operators get wrong: a Verify service (VA) and a Messaging
# service (MG) are both "service SIDs" in the console, and pasting the wrong one
# produces a Twilio rejection at send time that reads like an outage. Checking
# the shape at save time names the mistake where it was made.
_SID_SHAPE = re.compile(r"^[A-Z]{2}[0-9a-fA-F]{32}$")
_SID_TYPE_NAMES = {
    "AC": "an Account SID",
    "MG": "a Messaging Service SID",
    "VA": "a Verify Service SID",
    "SK": "an API Key SID",
    "PN": "a Phone Number SID",
    "MM": "a Message SID",
}


def _describe_sid(value: str) -> str:
    known = _SID_TYPE_NAMES.get(value[:2].upper())
    return known or f"a SID starting with {value[:2]}"


def _validate_sid(value: str, *, field: str, expected_prefix: str, label: str) -> None:
    """Reject a SID whose type prefix or shape is not what ``field`` needs.

    ``label`` is the bare noun phrase (e.g. "Account SID"), capitalized as it
    reads mid-sentence — callers must not prepend an article of their own.
    """
    if not value:
        return
    if value[:2].upper() != expected_prefix:
        raise PlatformSmsError(
            f"The {label} must start with {expected_prefix}. You entered "
            f"{_describe_sid(value)}. Copy the {label} from the Twilio console.",
            status_code=400,
            code=f"platform_sms_invalid_{field}",
        )
    if not _SID_SHAPE.match(value):
        raise PlatformSmsError(
            f"{label} does not look like a Twilio SID: it should be "
            f"{expected_prefix} followed by 32 hexadecimal characters.",
            status_code=400,
            code=f"platform_sms_invalid_{field}",
        )


def _validate_sender_number(value: str) -> None:
    if value and not _E164.match(value):
        raise PlatformSmsError(
            "Enter the From number in E.164 format, for example +15551234567.",
            status_code=400,
            code="platform_sms_invalid_from_number",
        )


def _validate_destination(to: str) -> str:
    normalized = _clean(to)
    if not _E164.match(normalized):
        raise PlatformSmsError(
            "Enter the destination in E.164 format, for example +15551234567.",
            status_code=400,
            code="platform_sms_invalid_recipient",
        )
    return normalized


def _provider_rejection(response: httpx.Response) -> PlatformSmsError:
    """Turn a non-2xx Twilio response into an error of the right severity.

    Every non-2xx used to become a 502. That mislabels the common case: bad
    credentials, a Verify SID pasted where a Messaging Service SID belongs, or
    an unusable From number are all *our caller's* configuration, not a failure
    of the origin. Worse, a 502 is exactly what an edge proxy replaces with its
    own error page, so the message Twilio gave us never reached the operator —
    which is how "the test send fails and the UI says nothing" happened.

    So: Twilio's 4xx become 4xx here and carry Twilio's own message and error
    code. Only Twilio being unavailable stays a 5xx.
    """
    message = ""
    provider_code = None
    try:
        payload = response.json() or {}
        message = str(payload.get("message") or "").strip()
        provider_code = payload.get("code")
    except Exception:  # noqa: BLE001 - provider body may be non-JSON
        payload = {}

    logger.warning(
        "Platform Twilio test send rejected (status=%s, code=%s)",
        response.status_code,
        provider_code,
    )

    if response.status_code == 429:
        return PlatformSmsError(
            message or "The SMS provider is rate limiting us. Try again shortly.",
            status_code=429,
            code="platform_sms_rate_limited",
            provider_status=response.status_code,
            provider_code=provider_code,
        )
    if response.status_code in (401, 403):
        return PlatformSmsError(
            message
            or (
                "Twilio rejected the Account SID and Auth Token. Check the "
                "credentials and that the token has not been rotated."
            ),
            status_code=400,
            code="platform_sms_provider_auth_failed",
            provider_status=response.status_code,
            provider_code=provider_code,
        )
    if 400 <= response.status_code < 500:
        return PlatformSmsError(
            message or "Twilio rejected the test message.",
            status_code=400,
            code="platform_sms_provider_rejected",
            provider_status=response.status_code,
            provider_code=provider_code,
        )
    return PlatformSmsError(
        "The SMS provider is unavailable. Try again.",
        status_code=502,
        code="platform_sms_provider_unavailable",
        provider_status=response.status_code,
        provider_code=provider_code,
    )


async def send_platform_test_sms(
    db: AsyncSession,
    *,
    to: str,
    body: str | None = None,
) -> dict:
    """Send one operator-initiated test message through the shared account."""

    destination = _validate_destination(to)
    credentials = await resolve_platform_sms_credentials(db)

    data: dict[str, str] = {
        "To": destination,
        "Body": _clean(body) or "LawHand SMS test message.",
    }
    if credentials.messaging_service_sid:
        data["MessagingServiceSid"] = credentials.messaging_service_sid
    elif credentials.from_number:
        data["From"] = credentials.from_number
    if credentials.status_callback_url:
        data["StatusCallback"] = credentials.status_callback_url

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                TWILIO_MESSAGES_URL.format(account_sid=credentials.account_sid),
                auth=(credentials.account_sid, credentials.auth_token),
                data=data,
            )
    except httpx.TimeoutException as exc:
        raise PlatformSmsError(
            "The SMS provider did not respond in time. Try again.",
            status_code=504,
            code="platform_sms_timeout",
        ) from exc
    except httpx.HTTPError as exc:
        raise PlatformSmsError(
            "The SMS provider could not be reached. Try again.",
            status_code=502,
            code="platform_sms_transport_error",
        ) from exc

    if response.status_code not in (200, 201):
        raise _provider_rejection(response)

    try:
        payload = response.json()
    except Exception:  # noqa: BLE001 - a 2xx with a non-JSON body is unusable
        raise PlatformSmsError(
            "The SMS provider returned an unreadable response.",
            status_code=502,
            code="platform_sms_provider_response_invalid",
        )
    return {
        "status": "sent",
        "sid": str(payload.get("sid") or ""),
        "provider_status": str(payload.get("status") or ""),
        "to": destination,
        "from_number": credentials.from_number,
        "messaging_service_sid": credentials.messaging_service_sid,
    }
