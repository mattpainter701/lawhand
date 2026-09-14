"""Platform shared Twilio sender: storage, masking, and test send."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.platform import PlatformSetting
from app.services import platform_sms
from app.services.token_vault import decrypt_token
from tests.platform_auth_helpers import platform_headers

ACCOUNT_SID = "AC" + "a" * 32  # Twilio SIDs are a 2-letter prefix plus 32 hex
AUTH_TOKEN = "super-secret-auth-token"
FROM_NUMBER = "+15550001111"


class _FakeResponse:
    def __init__(self, status_code=201, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"sid": "SM123", "status": "queued"}

    def json(self):
        return self._payload


class _FakeAsyncClient:
    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, auth=None, data=None):
        _FakeAsyncClient.calls.append({"url": url, "auth": auth, "data": data})
        return _FakeResponse()


@pytest.fixture
def fake_twilio(monkeypatch):
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(platform_sms.httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


async def _stored_config(db_session):
    return await db_session.scalar(
        select(PlatformSetting).where(
            PlatformSetting.key == platform_sms.PLATFORM_SMS_KEY
        )
    )


@pytest.mark.asyncio
async def test_provider_starts_unconfigured(client: AsyncClient):
    resp = await client.get("/api/platform/sms/provider", headers=platform_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["sender_ready"] is False


@pytest.mark.asyncio
async def test_provider_stores_token_encrypted_and_masks_it(
    client: AsyncClient, db_session
):
    resp = await client.put(
        "/api/platform/sms/provider",
        json={
            "account_sid": ACCOUNT_SID,
            "auth_token": AUTH_TOKEN,
            "from_number": FROM_NUMBER,
        },
        headers=platform_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["sender_ready"] is True
    assert body["auth_token_configured"] is True
    assert body["auth_token_hint"] == AUTH_TOKEN[-4:]
    assert AUTH_TOKEN not in resp.text
    assert ACCOUNT_SID not in resp.text

    stored = await _stored_config(db_session)
    assert stored is not None
    assert stored.value["encrypted_auth_token"] != AUTH_TOKEN
    assert decrypt_token(stored.value["encrypted_auth_token"]) == AUTH_TOKEN


@pytest.mark.asyncio
async def test_provider_update_keeps_token_when_omitted(client: AsyncClient, db_session):
    await client.put(
        "/api/platform/sms/provider",
        json={"account_sid": ACCOUNT_SID, "auth_token": AUTH_TOKEN, "from_number": FROM_NUMBER},
        headers=platform_headers(),
    )
    original = (await _stored_config(db_session)).value["encrypted_auth_token"]

    resp = await client.put(
        "/api/platform/sms/provider",
        json={"messaging_service_sid": "MG" + "b" * 32},
        headers=platform_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["auth_token_configured"] is True
    stored = await _stored_config(db_session)
    assert stored.value["encrypted_auth_token"] == original


@pytest.mark.asyncio
async def test_provider_rejects_incomplete_sender(client: AsyncClient):
    resp = await client.put(
        "/api/platform/sms/provider",
        json={"account_sid": ACCOUNT_SID, "auth_token": AUTH_TOKEN},
        headers=platform_headers(),
    )
    assert resp.status_code == 400
    # detail is structured so the UI can show a message and an operator can
    # act on the code; see test_platform_sms_errors.py for the full contract.
    detail = resp.json()["detail"]
    assert "Messaging Service" in detail["message"]
    assert detail["code"] == "platform_sms_incomplete"


@pytest.mark.asyncio
async def test_send_test_uses_saved_credentials(client: AsyncClient, fake_twilio):
    await client.put(
        "/api/platform/sms/provider",
        json={"account_sid": ACCOUNT_SID, "auth_token": AUTH_TOKEN, "from_number": FROM_NUMBER},
        headers=platform_headers(),
    )
    resp = await client.post(
        "/api/platform/sms/test",
        json={"to": "+15551234567", "body": "hello"},
        headers=platform_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["sid"] == "SM123"
    assert len(fake_twilio.calls) == 1
    call = fake_twilio.calls[0]
    assert call["url"].endswith(f"/Accounts/{ACCOUNT_SID}/Messages.json")
    assert call["auth"] == (ACCOUNT_SID, AUTH_TOKEN)
    assert call["data"]["From"] == FROM_NUMBER
    assert call["data"]["To"] == "+15551234567"


@pytest.mark.asyncio
async def test_send_test_requires_configuration(client: AsyncClient):
    resp = await client.post(
        "/api/platform/sms/test",
        json={"to": "+15551234567"},
        headers=platform_headers(),
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_send_test_rejects_non_e164(client: AsyncClient, fake_twilio):
    await client.put(
        "/api/platform/sms/provider",
        json={"account_sid": ACCOUNT_SID, "auth_token": AUTH_TOKEN, "from_number": FROM_NUMBER},
        headers=platform_headers(),
    )
    resp = await client.post(
        "/api/platform/sms/test",
        json={"to": "555-1234"},
        headers=platform_headers(),
    )
    assert resp.status_code == 400
    assert not fake_twilio.calls


@pytest.mark.asyncio
async def test_delete_provider_clears_configuration(client: AsyncClient, db_session):
    await client.put(
        "/api/platform/sms/provider",
        json={"account_sid": ACCOUNT_SID, "auth_token": AUTH_TOKEN, "from_number": FROM_NUMBER},
        headers=platform_headers(),
    )
    resp = await client.delete("/api/platform/sms/provider", headers=platform_headers())
    assert resp.status_code == 200
    assert await _stored_config(db_session) is None

    missing = await client.delete("/api/platform/sms/provider", headers=platform_headers())
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_platform_sms_requires_operator_scope(client: AsyncClient):
    resp = await client.get("/api/platform/sms/provider")
    assert resp.status_code == 403


# ── Issue #506: the reported configuration is refused with a usable message ──


@pytest.mark.asyncio
async def test_save_rejects_a_verify_sid_pasted_as_a_messaging_service_sid(
    client: AsyncClient,
):
    resp = await client.put(
        "/api/platform/sms/provider",
        json={
            "account_sid": ACCOUNT_SID,
            "auth_token": AUTH_TOKEN,
            "messaging_service_sid": "VA" + "c" * 32,
            "from_number": FROM_NUMBER,
        },
        headers=platform_headers(),
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "platform_sms_invalid_messaging_service_sid"
    assert "must start with MG" in detail["message"]
    assert "Verify Service SID" in detail["message"]


@pytest.mark.asyncio
async def test_save_rejects_a_from_number_that_is_not_e164(client: AsyncClient):
    resp = await client.put(
        "/api/platform/sms/provider",
        json={
            "account_sid": ACCOUNT_SID,
            "auth_token": AUTH_TOKEN,
            "from_number": "555-1234",
        },
        headers=platform_headers(),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "platform_sms_invalid_from_number"


@pytest.mark.asyncio
async def test_a_twilio_rejection_reaches_the_operator_as_a_400(
    client: AsyncClient, monkeypatch
):
    """The reported 502 was ours, not Twilio's.

    A 502 body is replaced by the edge proxy, so Twilio's message never
    arrived. A caller-side rejection is now a 400 whose body survives.
    """

    class _RejectingResponse:
        status_code = 400

        def json(self):
            return {"message": "The 'From' number is not a valid phone number", "code": 21606}

    class _RejectingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            return _RejectingResponse()

    await client.put(
        "/api/platform/sms/provider",
        json={
            "account_sid": ACCOUNT_SID,
            "auth_token": AUTH_TOKEN,
            "from_number": FROM_NUMBER,
        },
        headers=platform_headers(),
    )
    monkeypatch.setattr(platform_sms.httpx, "AsyncClient", _RejectingClient)

    resp = await client.post(
        "/api/platform/sms/test",
        json={"to": "+17015273866", "body": "lawhand test"},
        headers=platform_headers(),
    )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "not a valid phone number" in detail["message"]
    assert detail["provider_code"] == 21606
    assert detail["provider_status"] == 400


@pytest.mark.asyncio
async def test_a_sender_stored_before_validation_existed_is_still_reported(
    client: AsyncClient, db_session
):
    """A bad SID saved earlier must not reach Twilio and come back as a 502."""
    db_session.add(
        PlatformSetting(
            key=platform_sms.PLATFORM_SMS_KEY,
            value={
                "provider": "twilio",
                "account_sid": ACCOUNT_SID,
                "encrypted_auth_token": platform_sms.encrypt_token(AUTH_TOKEN),
                "messaging_service_sid": "VA" + "c" * 32,
                "is_active": True,
            },
        )
    )
    await db_session.commit()

    resp = await client.post(
        "/api/platform/sms/test",
        json={"to": "+17015273866"},
        headers=platform_headers(),
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "platform_sms_invalid_messaging_service_sid"
