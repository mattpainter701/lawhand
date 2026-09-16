"""The shared Twilio sender says what went wrong, at the right severity.

Issue #506: saving the sender and sending a test both failed with bare 400s
that showed nothing actionable, and a retry produced a 502 from the edge proxy.

The 502 is the explained half. Every non-2xx from Twilio used to become a 502,
so a caller-side configuration mistake — the reporter pasted a Verify service
SID (VA…) where a Messaging Service SID (MG…) belongs, with a placeholder From
number — was reported as a failure of our origin. An edge proxy replaces a 502
body with its own error page, so the message Twilio gave us never reached the
operator. Twilio's 4xx are now our 4xx and carry Twilio's own message and code;
only Twilio being unavailable stays a 5xx.
"""

import httpx
import pytest

from app.services import platform_sms
from app.services.platform_sms import (
    PlatformSmsError,
    _provider_rejection,
    _validate_sender_number,
    _validate_sid,
    _validate_status_callback_url,
)

ACCOUNT_SID = "AC" + "a" * 32
MESSAGING_SID = "MG" + "b" * 32
VERIFY_SID = "VA" + "c" * 32


def _response(status_code, payload=None):
    return httpx.Response(
        status_code,
        json=payload if payload is not None else {},
        request=httpx.Request("POST", "https://api.twilio.com/"),
    )


# ── SID shape: name the mistake where it was made ────────────────────────────


def test_a_verify_sid_pasted_as_a_messaging_service_sid_is_named():
    with pytest.raises(PlatformSmsError) as exc_info:
        _validate_sid(
            VERIFY_SID,
            field="messaging_service_sid",
            expected_prefix="MG",
            label="Messaging Service SID",
        )
    error = exc_info.value
    assert error.status_code == 400
    assert error.code == "platform_sms_invalid_messaging_service_sid"
    # The operator is told which value they pasted, not just that it is wrong.
    assert "must start with MG" in str(error)
    assert "Verify Service SID" in str(error)
    # Both clauses carry exactly one article; the console line names the same
    # field the operator typed into, not a "stored" variant of it.
    assert str(error) == (
        "The Messaging Service SID must start with MG. You entered a Verify "
        "Service SID. Copy the Messaging Service SID from the Twilio console."
    )


def test_an_account_sid_in_the_wrong_field_is_named_too():
    with pytest.raises(PlatformSmsError) as exc_info:
        _validate_sid(
            ACCOUNT_SID,
            field="messaging_service_sid",
            expected_prefix="MG",
            label="Messaging Service SID",
        )
    assert "an Account SID" in str(exc_info.value)


def test_an_unrecognised_prefix_is_still_rejected_without_guessing():
    with pytest.raises(PlatformSmsError) as exc_info:
        _validate_sid(
            "ZZ" + "d" * 32,
            field="account_sid",
            expected_prefix="AC",
            label="Account SID",
        )
    assert "starting with ZZ" in str(exc_info.value)


def test_a_truncated_sid_is_rejected_on_shape():
    with pytest.raises(PlatformSmsError) as exc_info:
        _validate_sid(
            "AC123",
            field="account_sid",
            expected_prefix="AC",
            label="Account SID",
        )
    assert "32 hexadecimal" in str(exc_info.value)
    assert str(exc_info.value).startswith(
        "The Account SID does not look like a Twilio SID"
    )


@pytest.mark.asyncio
async def test_a_stored_sid_is_validated_before_a_send(monkeypatch):
    """A sender saved before shape checks existed still names the bad field."""

    async def _config(_db):
        return {
            "account_sid": ACCOUNT_SID,
            "encrypted_auth_token": "enc",
            "messaging_service_sid": "MG123",
            "from_number": None,
            "is_active": True,
        }

    monkeypatch.setattr(platform_sms, "get_platform_sms_config", _config)
    monkeypatch.setattr(platform_sms, "decrypt_token", lambda _value: "token")

    with pytest.raises(PlatformSmsError) as exc_info:
        await platform_sms.resolve_platform_sms_credentials(None)

    message = str(exc_info.value)
    assert message.startswith(
        "The Messaging Service SID does not look like a Twilio SID"
    )
    assert "Copy the Messaging Service SID from the Twilio console" not in message


def test_a_wellformed_sid_passes():
    _validate_sid(
        ACCOUNT_SID, field="account_sid", expected_prefix="AC", label="Account SID"
    )
    _validate_sid(
        MESSAGING_SID,
        field="messaging_service_sid",
        expected_prefix="MG",
        label="Messaging Service SID",
    )


def test_an_absent_sid_is_not_a_shape_error():
    # Completeness is a separate check with its own message.
    _validate_sid(
        "", field="messaging_service_sid", expected_prefix="MG", label="MG SID"
    )


def test_a_non_e164_sender_number_is_rejected_at_save_time():
    with pytest.raises(PlatformSmsError) as exc_info:
        _validate_sender_number("5551234567")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "platform_sms_invalid_from_number"


def test_an_e164_sender_number_passes():
    _validate_sender_number("+15551234567")


def test_a_non_https_status_callback_url_is_rejected():
    with pytest.raises(PlatformSmsError) as exc_info:
        _validate_status_callback_url("http://firm.example/sms-status")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "platform_sms_invalid_status_callback_url"
    assert "https://" in str(exc_info.value)


def test_a_relative_status_callback_url_is_rejected():
    # Twilio needs an absolute URL it can reach; a path would silently never fire.
    with pytest.raises(PlatformSmsError):
        _validate_status_callback_url("/sms-status")


def test_an_https_status_callback_url_passes():
    _validate_status_callback_url("https://firm.example/sms-status")


def test_an_absent_status_callback_url_is_allowed():
    _validate_status_callback_url("")


# ── Provider rejections are classified by whose fault they are ───────────────


def test_a_twilio_rejection_is_a_caller_error_not_a_bad_gateway():
    # This is the reported case: Twilio rejects the request because of what we
    # sent it. Reporting that as 502 is what let an edge proxy swallow the
    # message and leave the operator with nothing.
    error = _provider_rejection(
        _response(
            400,
            {
                "message": "The 'From' number +15551234567 is not a valid...",
                "code": 21606,
            },
        )
    )
    assert error.status_code == 400
    assert error.code == "platform_sms_provider_rejected"
    assert "not a valid" in str(error)
    # Twilio's own error number, so an operator can look it up.
    assert error.provider_code == 21606
    assert error.provider_status == 400


def test_bad_credentials_are_reported_as_a_credentials_problem():
    error = _provider_rejection(_response(401, {"message": "Authenticate"}))
    assert error.status_code == 400
    assert error.code == "platform_sms_provider_auth_failed"


def test_a_credentials_failure_without_a_body_still_explains_itself():
    error = _provider_rejection(_response(403))
    assert error.status_code == 400
    assert "Account SID and Auth Token" in str(error)


def test_rate_limiting_keeps_its_own_status():
    error = _provider_rejection(_response(429, {"message": "Too many requests"}))
    assert error.status_code == 429
    assert error.code == "platform_sms_rate_limited"


def test_twilio_being_down_is_the_only_thing_that_stays_a_bad_gateway():
    error = _provider_rejection(_response(503, {"message": "Service unavailable"}))
    assert error.status_code == 502
    assert error.code == "platform_sms_provider_unavailable"


def test_a_non_json_rejection_body_does_not_crash_the_handler():
    response = httpx.Response(
        400,
        content=b"<html>gateway</html>",
        request=httpx.Request("POST", "https://api.twilio.com/"),
    )
    error = _provider_rejection(response)
    assert error.status_code == 400
    assert str(error) == "Twilio rejected the test message."


def test_an_unavailable_provider_never_leaks_its_body_to_the_operator():
    # A 5xx body is about Twilio's infrastructure, not something to act on.
    error = _provider_rejection(_response(500, {"message": "internal db error host-7"}))
    assert "host-7" not in str(error)


# ── Transport failures ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_timeout_is_a_gateway_timeout_not_a_silent_502(monkeypatch):
    class _TimingOutClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("timed out")

    async def _credentials(db):
        return platform_sms.PlatformSmsCredentials(
            account_sid=ACCOUNT_SID,
            auth_token="token",
            messaging_service_sid=MESSAGING_SID,
            from_number=None,
            status_callback_url=None,
        )

    monkeypatch.setattr(platform_sms.httpx, "AsyncClient", _TimingOutClient)
    monkeypatch.setattr(platform_sms, "resolve_platform_sms_credentials", _credentials)

    with pytest.raises(PlatformSmsError) as exc_info:
        await platform_sms.send_platform_test_sms(None, to="+17015273866")
    assert exc_info.value.status_code == 504
    assert exc_info.value.code == "platform_sms_timeout"


@pytest.mark.asyncio
async def test_an_unreachable_provider_is_a_bad_gateway(monkeypatch):
    class _UnreachableClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("no route to host")

    async def _credentials(db):
        return platform_sms.PlatformSmsCredentials(
            account_sid=ACCOUNT_SID,
            auth_token="token",
            messaging_service_sid=MESSAGING_SID,
            from_number=None,
            status_callback_url=None,
        )

    monkeypatch.setattr(platform_sms.httpx, "AsyncClient", _UnreachableClient)
    monkeypatch.setattr(platform_sms, "resolve_platform_sms_credentials", _credentials)

    with pytest.raises(PlatformSmsError) as exc_info:
        await platform_sms.send_platform_test_sms(None, to="+17015273866")
    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "platform_sms_transport_error"
