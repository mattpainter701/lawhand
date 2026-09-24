"""POST /api/email/scan may only read the caller's own mailbox.

The endpoint used to accept any ``user_id`` in the body and scan that user's
mailbox with their delegated grant, returning subjects, senders, AI summaries
and draft replies to whoever asked.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import email_agent as router
from app.schemas.email_agent import EmailScanRequest


def _request(tenant_id):
    return SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))


@pytest.mark.asyncio
async def test_scanning_another_users_mailbox_is_refused(monkeypatch):
    caller = SimpleNamespace(id=uuid.uuid4(), tenant=None, privacy_mode=False)

    async def current_user(*_args):
        return caller

    processed = []

    async def process_emails(**kwargs):
        processed.append(kwargs)
        return []

    monkeypatch.setattr(router, "get_current_user", current_user)
    monkeypatch.setattr(router.email_agent, "process_emails", process_emails)

    with pytest.raises(HTTPException) as refused:
        await router.scan_emails(
            EmailScanRequest(provider="microsoft", user_id=str(uuid.uuid4())),
            _request(str(uuid.uuid4())),
            db=None,
        )

    assert refused.value.status_code == 403
    assert processed == []


@pytest.mark.asyncio
async def test_scanning_your_own_mailbox_still_works(monkeypatch):
    caller = SimpleNamespace(id=uuid.uuid4(), tenant=None, privacy_mode=False)
    tenant_id = str(uuid.uuid4())

    async def current_user(*_args):
        return caller

    async def noop(*_args, **_kwargs):
        return None

    async def route(*_args, **_kwargs):
        return SimpleNamespace(model="standard")

    async def premium(*_args, **_kwargs):
        return False

    processed = []

    async def process_emails(**kwargs):
        processed.append(kwargs)
        return []

    monkeypatch.setattr(router, "get_current_user", current_user)
    monkeypatch.setattr(router, "set_tenant_context", noop)
    monkeypatch.setattr(router, "resolve_llm_route", route)
    monkeypatch.setattr(router, "resolve_user_premium_ai", premium)
    monkeypatch.setattr(router, "LLMService", lambda: object())
    monkeypatch.setattr(router.email_agent, "process_emails", process_emails)

    for body in (
        EmailScanRequest(provider="microsoft"),
        EmailScanRequest(provider="microsoft", user_id=str(caller.id)),
    ):
        response = await router.scan_emails(body, _request(tenant_id), db=None)
        assert response.user_id == str(caller.id)

    assert [call["user_id"] for call in processed] == [str(caller.id)] * 2
