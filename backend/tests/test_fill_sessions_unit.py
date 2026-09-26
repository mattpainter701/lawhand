"""Pure helpers of the fill-session background save (no database)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.fill_session import FillSessionRenderRequest
from app.services import fill_sessions
from app.services.fill_sessions import _member_has_durable_save, _merge_member_statuses


def test_durable_member_save_is_the_retry_boundary():
    assert _member_has_durable_save(
        {"status": "saved", "matter_document_id": "document-1"}
    )
    assert not _member_has_durable_save({"status": "saved"})
    assert not _member_has_durable_save(
        {"status": "failed", "matter_document_id": "document-1"}
    )


class _FakeDB:
    def __init__(self):
        self.commits = 0
        self.refreshes = 0

    async def commit(self):
        self.commits += 1

    async def refresh(self, _session):
        self.refreshes += 1


def _render_payload(*template_ids):
    return FillSessionRenderRequest(
        members=[
            {"template_id": template_id, "variables": {"name": "Ada"}}
            for template_id in template_ids
        ]
    )


@pytest.mark.asyncio
async def test_enqueue_render_filters_durable_members(monkeypatch):
    saved_id, failed_id = uuid4(), uuid4()
    session = SimpleNamespace(
        id=uuid4(),
        answers_sha256="answers",
        status="failed",
        last_error="1 of 2 documents were not saved.",
        matter_id=uuid4(),
        tenant_id=uuid4(),
        members_json=[
            {
                "template_id": str(saved_id),
                "status": "saved",
                "matter_document_id": str(uuid4()),
            },
            {"template_id": str(failed_id), "status": "failed", "detail": "retry"},
        ],
    )
    db = _FakeDB()
    sealed = []
    enqueued = []
    jobs = []

    async def own_session(*_args, **_kwargs):
        return session

    async def fake_enqueue(*_args, **kwargs):
        enqueued.append(kwargs["payload"])
        job = SimpleNamespace(id=uuid4(), payload=kwargs["payload"])
        jobs.append(job)
        return job

    async def fake_set_tenant_context(*_args):
        return None

    monkeypatch.setattr(fill_sessions, "_own_session", own_session)
    monkeypatch.setattr(fill_sessions, "set_tenant_context", fake_set_tenant_context)
    monkeypatch.setattr(
        fill_sessions,
        "_seal_members",
        lambda members: sealed.append(members) or "sealed",
    )
    monkeypatch.setattr(fill_sessions, "enqueue_job", fake_enqueue)

    result = await fill_sessions.enqueue_render(
        db,
        SimpleNamespace(id=uuid4()),
        uuid4(),
        _render_payload(saved_id, failed_id),
    )

    assert result.status == "saving"
    assert [member["template_id"] for member in sealed[0]] == [str(failed_id)]
    assert enqueued[0]["members_ciphertext"] == "sealed"
    assert enqueued[0]["session_answers_sha256"] == "answers"
    assert jobs[0].payload["job_id"] == str(result.job_id)
    statuses = {item["template_id"]: item for item in result.members_json}
    assert statuses[str(saved_id)]["status"] == "saved"
    assert statuses[str(failed_id)]["status"] == "queued"


@pytest.mark.asyncio
async def test_enqueue_render_rejects_duplicate_template_members_before_mutation(
    monkeypatch,
):
    template_id = uuid4()
    session = SimpleNamespace(
        status="failed",
        matter_id=uuid4(),
        tenant_id=uuid4(),
        members_json=[],
    )
    db = _FakeDB()

    async def own_session(*_args, **_kwargs):
        return session

    async def unexpected_enqueue(*_args, **_kwargs):
        raise AssertionError("duplicate members must be rejected before enqueue")

    monkeypatch.setattr(fill_sessions, "_own_session", own_session)
    monkeypatch.setattr(fill_sessions, "enqueue_job", unexpected_enqueue)
    with pytest.raises(HTTPException, match="each template only once"):
        await fill_sessions.enqueue_render(
            db,
            SimpleNamespace(id=uuid4()),
            uuid4(),
            _render_payload(template_id, template_id),
        )

    assert session.status == "failed"
    assert session.members_json == []
    assert db.commits == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("has_other_failed", "expected_status", "expected_error"),
    [
        (False, "saved", None),
        (True, "open", "1 of 2 documents were not saved."),
    ],
)
async def test_enqueue_render_all_requested_saved_is_a_noop(
    monkeypatch, has_other_failed, expected_status, expected_error
):
    saved_id, failed_id = uuid4(), uuid4()
    prior = [
        {
            "template_id": str(saved_id),
            "status": "saved",
            "matter_document_id": "doc",
        }
    ]
    if has_other_failed:
        prior.append(
            {"template_id": str(failed_id), "status": "failed", "detail": "retry"}
        )
    session = SimpleNamespace(
        status="failed",
        last_error="1 of 2 documents were not saved.",
        matter_id=uuid4(),
        tenant_id=uuid4(),
        members_json=prior,
    )
    db = _FakeDB()
    enqueue_calls = []

    async def own_session(*_args, **_kwargs):
        return session

    async def fake_enqueue(*_args, **_kwargs):
        enqueue_calls.append(True)

    async def fake_set_tenant_context(*_args):
        return None

    monkeypatch.setattr(fill_sessions, "_own_session", own_session)
    monkeypatch.setattr(fill_sessions, "set_tenant_context", fake_set_tenant_context)
    monkeypatch.setattr(fill_sessions, "enqueue_job", fake_enqueue)

    result = await fill_sessions.enqueue_render(
        db,
        SimpleNamespace(id=uuid4()),
        uuid4(),
        _render_payload(saved_id),
    )

    assert result.status == expected_status
    assert result.last_error == expected_error
    assert enqueue_calls == []
    assert db.commits == 1


def test_merge_keeps_an_earlier_members_outcome_and_orders_by_packet():
    prior = {
        "a": {"template_id": "a", "status": "saved", "matter_document_id": "d1"},
        "b": {"template_id": "b", "status": "queued"},
    }
    members = [{"template_id": "b", "variables": {}}]
    outcomes = [{"template_id": "b", "status": "saved", "matter_document_id": "d2"}]

    merged = _merge_member_statuses(prior, members, outcomes)

    assert [entry["template_id"] for entry in merged] == ["b", "a"]
    assert merged[0] == outcomes[0]
    # The member an earlier attempt saved survives a retry that did not carry it.
    assert merged[1] == prior["a"]


def test_merge_marks_members_not_yet_processed_as_queued():
    merged = _merge_member_statuses({}, [{"template_id": "x"}], [])

    assert merged == [{"template_id": "x", "status": "queued"}]
