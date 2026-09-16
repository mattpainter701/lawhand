"""A signing plan the server guessed at is looked at before it is sent.

``build_plan`` never fails: when nothing on the page says where a role signs
it invents a block at the foot of the last page, and when it finds too much
it offers all of it. Both are guesses. Until now they went straight to the
client, and the client was the first person to see a signature box in the
wrong place. The plan now reviews itself, the request carries the review, and
the send endpoint refuses a plan with warnings until staff acknowledge them.
"""

from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.routers.esignature as router
from app.models.signature import SignatureRequest, SignatureSigner
from app.schemas.signature import SignatureRequestSend
from app.services.esign.plan import (
    MAX_LINES_PER_SIGNER,
    PlanField,
    SignerRef,
    SigningPlan,
    build_plan,
)
from tests.esign_pdf_fixtures import acroform_pdf, blank_pdf, flat_agreement_pdf
from tests.esign_real_layouts import parenting_plan_pdf, stipulation_pdf

CLIENT = SignerRef("s-client", "Jane Client", "client", 0)
ATTORNEY = SignerRef("s-attorney", "Ann Attorney", "attorney", 1)
PLAINTIFF = SignerRef("s-plaintiff", "Pat Example", "plaintiff", 0)


def _plan(*fields, fill_supported=True, error=None, left_for_others=()):
    return SigningPlan(
        source_sha256="a" * 64,
        pages=[{"page": 1, "width": 612.0, "height": 792.0}],
        fields=list(fields),
        fill_supported=fill_supported,
        error=error,
        left_for_others=list(left_for_others),
    )


def _sig(role, source="detected", label="Signature", index=0):
    return PlanField(
        field_id=f"auto:sig:{index}",
        kind="signature",
        page=1,
        rect=(72.0, 100.0, 272.0, 128.0),
        label=label,
        required=True,
        role=role,
        source=source,
    )


def codes(plan):
    return [(item["level"], item["code"], item["role"]) for item in plan.review()]


# ── What the plan says about itself ─────────────────────────────────────────


def test_a_plan_that_found_every_line_has_nothing_to_warn_about():
    plan = build_plan(flat_agreement_pdf(), signers=[CLIENT])

    assert [item for item in plan.review() if item["level"] == "warn"] == []
    assert plan.review_required is False
    # The attorney's printed line was left alone, and that is worth saying.
    [info] = plan.review()
    assert info["code"] == "left_for_others" and "Attorney" in info["detail"]


def test_a_form_with_its_own_signature_widget_has_nothing_to_review():
    plan = build_plan(acroform_pdf(), signers=[CLIENT])

    assert plan.review() == []


def test_a_signer_placed_by_fallback_is_a_warning_naming_them():
    plan = build_plan(blank_pdf(), signers=[CLIENT, ATTORNEY])

    assert codes(plan) == [
        ("warn", "fallback", "client"),
        ("warn", "fallback", "attorney"),
    ]
    assert plan.review_required is True
    assert "foot of the last page" in plan.review()[0]["detail"]


def test_only_the_signer_who_fell_back_is_named():
    plan = build_plan(flat_agreement_pdf(), signers=[CLIENT, ATTORNEY])

    # The client's line was printed; the attorney's rule sits under a label
    # this fixture draws, so both are detected -- nothing to warn about.
    assert [item for item in codes(plan) if item[1] == "fallback"] == []


def test_too_many_places_for_one_signer_is_a_warning():
    plan = _plan(*(_sig("client", index=i) for i in range(MAX_LINES_PER_SIGNER + 1)))

    assert codes(plan) == [("warn", "many_lines", "client")]
    assert str(MAX_LINES_PER_SIGNER + 1) in plan.review()[0]["detail"]


def test_exactly_the_bound_is_not_a_warning():
    plan = _plan(*(_sig("client", index=i) for i in range(MAX_LINES_PER_SIGNER)))

    assert plan.review() == []


def test_an_unreadable_form_is_a_warning_with_the_reason():
    plan = _plan(fill_supported=False, error="Widgets we cannot render safely")

    assert codes(plan) == [("warn", "unsupported", "")]
    assert plan.review()[0]["detail"] == "Widgets we cannot render safely"


def test_lines_left_for_other_parties_are_reported_as_information():
    plan = build_plan(stipulation_pdf(), signers=[PLAINTIFF])

    info = [item for item in plan.review() if item["level"] == "info"]
    assert [item["code"] for item in info] == ["left_for_others"]
    assert "Notary Public" in info[0]["detail"] and "Defendant" in info[0]["detail"]
    # Information alone does not hold up sending.
    assert plan.review_required is False


def test_the_parenting_plan_sent_to_the_wrong_role_warns_and_explains():
    """A client role on a parents' document: fallback, and whose lines were left."""
    plan = build_plan(parenting_plan_pdf(), signers=[CLIENT])

    levels = {item["code"]: item["level"] for item in plan.review()}
    assert levels == {"fallback": "warn", "left_for_others": "info"}


def test_the_summary_carries_the_review_to_the_request_row():
    plan = build_plan(blank_pdf(), signers=[CLIENT])
    summary = plan.summary()

    assert summary["review_required"] is True
    assert [item["code"] for item in summary["review"]] == ["fallback"]


def test_a_warning_names_the_role_as_the_signer_form_shows_it():
    plan = _plan(_sig("co_client", source="fallback"))

    assert plan.review()[0]["role"] == "co_client"
    assert "co_client" in plan.review()[0]["detail"]


# ── The request carries it ──────────────────────────────────────────────────


def _row(status="draft", signing_plan=None):
    row = SignatureRequest(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        matter_id=uuid.uuid4(),
        status=status,
        provider="internal",
        source_document_filename="Fee agreement.pdf",
        signing_plan=signing_plan,
    )
    row.signers = [
        SignatureSigner(
            id=uuid.uuid4(),
            name="Client",
            email="client@example.com",
            status="pending",
            sign_order=0,
        )
    ]
    return row


def test_a_request_planned_before_the_review_existed_needs_no_acknowledgement():
    summary = router._plan_summary(_row(signing_plan={"fill_supported": True}))

    assert summary["plan_review"] == [] and summary["plan_review_required"] is False


def test_a_request_with_no_stored_plan_needs_no_acknowledgement():
    summary = router._plan_summary(_row(signing_plan=None))

    assert summary["plan_review_required"] is False


def test_the_stored_review_is_read_back_and_garbage_is_dropped():
    summary = router._plan_summary(
        _row(
            signing_plan={
                "review": [{"level": "warn", "code": "fallback", "detail": "x"}, "junk", 3],
                "review_required": True,
            }
        )
    )

    assert summary["plan_review"] == [{"level": "warn", "code": "fallback", "detail": "x"}]
    assert summary["plan_review_required"] is True


def test_the_block_message_lists_the_warnings_and_what_to_do():
    detail = router._review_block_detail(
        [
            {"level": "warn", "code": "fallback", "detail": "No line for client."},
            {"level": "info", "code": "left_for_others", "detail": "Left Defendant."},
        ],
        filename="Stipulation.pdf",
    )

    assert detail.startswith('"Stipulation.pdf" has a signing plan that needs a look')
    assert "No line for client." in detail
    assert "Left Defendant." not in detail
    assert "confirm" in detail


# ── The send endpoint insists ───────────────────────────────────────────────


class _Db:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def _http_request():
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)})


def _wire(monkeypatch, row, sent):
    class Provider:
        async def send(self, request):
            sent.append(request)
            return "envelope-1"

    async def current_user(*args):
        return SimpleNamespace(tenant_id=row.tenant_id)

    async def load(*args):
        return row

    async def no_op(*args):
        return None

    async def unchanged(*args):
        return True

    async def response(_db, request):
        return request

    monkeypatch.setattr(router, "get_current_user", current_user)
    monkeypatch.setattr(router, "set_tenant_context", no_op)
    monkeypatch.setattr(router, "_load_request", load)
    monkeypatch.setattr(router, "_expire_and_commit_if_needed", no_op)
    monkeypatch.setattr(router, "_source_document_is_unchanged", unchanged)
    monkeypatch.setattr(router, "get_provider", lambda name: Provider())
    monkeypatch.setattr(router, "notify_actionable_signers", no_op)
    monkeypatch.setattr(router, "notify_actionable_signers_sms", no_op)
    monkeypatch.setattr(router, "ensure_signature_followup", no_op)
    monkeypatch.setattr(router, "_to_response", response)


GUESSED = {
    "fill_supported": True,
    "review": [
        {
            "level": "warn",
            "code": "fallback",
            "role": "client",
            "detail": "No signature line was found for client.",
        }
    ],
    "review_required": True,
}


@pytest.mark.asyncio
async def test_a_guessed_plan_is_not_sent_until_staff_acknowledge_it(monkeypatch):
    row = _row(signing_plan=GUESSED)
    sent = []
    _wire(monkeypatch, row, sent)

    with pytest.raises(HTTPException) as refused:
        await router.send_signature_request(
            str(row.matter_id), str(row.id), _http_request(), _Db()
        )

    assert refused.value.status_code == 422
    assert "No signature line was found for client." in refused.value.detail
    assert '"Fee agreement.pdf"' in refused.value.detail
    assert sent == [] and row.status == "draft"


@pytest.mark.asyncio
async def test_an_explicit_acknowledgement_sends_it(monkeypatch):
    row = _row(signing_plan=GUESSED)
    sent = []
    _wire(monkeypatch, row, sent)

    await router.send_signature_request(
        str(row.matter_id),
        str(row.id),
        _http_request(),
        _Db(),
        SignatureRequestSend(acknowledge_review=True),
    )

    assert len(sent) == 1 and row.status == "sent"


@pytest.mark.asyncio
async def test_a_plan_with_nothing_to_review_sends_as_before(monkeypatch):
    row = _row(signing_plan={"fill_supported": True, "review": [], "review_required": False})
    sent = []
    _wire(monkeypatch, row, sent)

    await router.send_signature_request(
        str(row.matter_id), str(row.id), _http_request(), _Db()
    )

    assert len(sent) == 1 and row.status == "sent"


@pytest.mark.asyncio
async def test_information_only_findings_do_not_hold_up_sending(monkeypatch):
    row = _row(
        signing_plan={
            "review": [{"level": "info", "code": "left_for_others", "detail": "x"}],
            "review_required": False,
        }
    )
    sent = []
    _wire(monkeypatch, row, sent)

    await router.send_signature_request(
        str(row.matter_id), str(row.id), _http_request(), _Db()
    )

    assert len(sent) == 1


@pytest.mark.asyncio
async def test_acknowledging_a_clean_plan_is_harmless(monkeypatch):
    row = _row(signing_plan={"review": [], "review_required": False})
    sent = []
    _wire(monkeypatch, row, sent)

    await router.send_signature_request(
        str(row.matter_id),
        str(row.id),
        _http_request(),
        _Db(),
        SignatureRequestSend(acknowledge_review=True),
    )

    assert len(sent) == 1


def test_the_default_send_body_does_not_acknowledge():
    assert SignatureRequestSend().acknowledge_review is False
