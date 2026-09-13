"""API tests for the billing overhaul: live timers, draft invoice workflow,
sequential numbering, status transitions, and void-release behavior."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plugin import Matter


@pytest_asyncio.fixture
async def test_matter(db_session: AsyncSession, test_tenant, test_user):
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"test-matter-{uuid.uuid4().hex[:8]}",
        matter_name="Smith v. Jones",
        matter_type="litigation",
        counterparty="Acme Corp",
        hourly_rate=Decimal("250.00"),
    )
    db_session.add(matter)
    await db_session.commit()
    await db_session.refresh(matter)
    return matter


async def _log_time(client, matter_id: str, hours: str = "2.0") -> dict:
    resp = await client.post(
        "/api/billing/time-entries",
        json={
            "matter_id": str(matter_id),
            "description": "Drafted motion",
            "hours": hours,
            "date": "2026-07-01",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestTimer:
    async def test_start_stop_timer(self, client, test_matter):
        start = await client.post(
            "/api/billing/time-entries/timer/start",
            json={"matter_id": str(test_matter.id), "description": "Research"},
        )
        assert start.status_code == 201, start.text
        started = start.json()
        assert started["status"] == "running"
        assert started["timer_started_at"] is not None
        assert Decimal(started["hourly_rate"]) == Decimal("250.00")

        active = await client.get("/api/billing/time-entries/timer")
        assert active.status_code == 200
        assert active.json()["id"] == started["id"]

        stop = await client.post("/api/billing/time-entries/timer/stop", json={})
        assert stop.status_code == 200, stop.text
        stopped = stop.json()
        assert stopped["status"] == "draft"
        assert stopped["timer_started_at"] is None
        # Even a near-instant stop bills the minimum 6-minute increment
        assert Decimal(stopped["hours"]) == Decimal("0.10")
        assert Decimal(stopped["amount"]) == Decimal("25.00")

    async def test_only_one_running_timer(self, client, test_matter):
        first = await client.post(
            "/api/billing/time-entries/timer/start",
            json={"matter_id": str(test_matter.id)},
        )
        assert first.status_code == 201
        second = await client.post(
            "/api/billing/time-entries/timer/start",
            json={"matter_id": str(test_matter.id)},
        )
        assert second.status_code == 409

    async def test_cancel_timer_discards_entry(self, client, test_matter):
        start = await client.post(
            "/api/billing/time-entries/timer/start",
            json={"matter_id": str(test_matter.id)},
        )
        entry_id = start.json()["id"]

        cancel = await client.delete("/api/billing/time-entries/timer")
        assert cancel.status_code == 204

        gone = await client.get(f"/api/billing/time-entries/{entry_id}")
        assert gone.status_code == 404

    async def test_stop_without_timer_404(self, client):
        resp = await client.post("/api/billing/time-entries/timer/stop", json={})
        assert resp.status_code == 404

    async def test_running_entry_excluded_from_invoice(self, client, test_matter):
        await client.post(
            "/api/billing/time-entries/timer/start",
            json={"matter_id": str(test_matter.id)},
        )
        resp = await client.post(
            "/api/billing/invoices/generate",
            json={"matter_id": str(test_matter.id)},
        )
        # Only a running timer exists → nothing billable yet
        assert resp.status_code == 400


class TestInvoiceWorkflow:
    async def test_preview_and_selected_sources(self, client, test_matter):
        first = await _log_time(client, test_matter.id, hours="1.0")
        second = await _log_time(client, test_matter.id, hours="2.0")
        preview = await client.get(
            "/api/billing/invoices/preview", params={"matter_id": str(test_matter.id)}
        )
        assert preview.status_code == 200, preview.text
        assert {x["id"] for x in preview.json()["time_entries"]} == {
            first["id"],
            second["id"],
        }
        generated = await client.post(
            "/api/billing/invoices/generate",
            json={
                "matter_id": str(test_matter.id),
                "time_entry_ids": [first["id"]],
                "expense_ids": [],
            },
        )
        assert generated.status_code == 201, generated.text
        assert len(generated.json()["line_items"]) == 1

    async def test_overpayment_and_direct_paid_are_rejected(self, client, test_matter):
        await _log_time(client, test_matter.id, hours="1.0")
        inv = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()
        assert (
            await client.patch(
                f"/api/billing/invoices/{inv['id']}", json={"status": "paid"}
            )
        ).status_code == 400
        assert (
            await client.patch(
                f"/api/billing/invoices/{inv['id']}", json={"status": "sent"}
            )
        ).status_code == 200
        over = await client.post(
            "/api/billing/payments",
            json={
                "invoice_id": inv["id"],
                "amount": str(Decimal(inv["total"]) + Decimal("0.01")),
                "payment_date": "2026-07-02",
            },
        )
        assert over.status_code == 400

    async def test_generate_creates_draft_with_sequential_number(
        self, client, test_matter
    ):
        await _log_time(client, test_matter.id)
        resp = await client.post(
            "/api/billing/invoices/generate",
            json={"matter_id": str(test_matter.id)},
        )
        assert resp.status_code == 201, resp.text
        inv = resp.json()
        assert inv["status"] == "draft"
        year = inv["issue_date"][:4]
        assert inv["invoice_number"] == f"INV-{year}-0001"
        assert Decimal(inv["balance_due"]) == Decimal(inv["total"])
        assert inv["matter_name"] == "Smith v. Jones"
        assert inv["billing_period_start"] == "2026-07-01"

        # Second invoice gets the next sequence number
        await _log_time(client, test_matter.id, hours="1.0")
        resp2 = await client.post(
            "/api/billing/invoices/generate",
            json={"matter_id": str(test_matter.id)},
        )
        assert resp2.status_code == 201
        assert resp2.json()["invoice_number"] == f"INV-{year}-0002"

    async def test_draft_cannot_jump_to_paid(self, client, test_matter):
        await _log_time(client, test_matter.id)
        inv = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()

        resp = await client.patch(
            f"/api/billing/invoices/{inv['id']}", json={"status": "paid"}
        )
        assert resp.status_code == 400

    async def test_send_then_pay_flow(self, client, test_matter):
        await _log_time(client, test_matter.id)
        inv = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()

        # Payments are blocked while the invoice is a draft
        blocked = await client.post(
            "/api/billing/payments",
            json={
                "invoice_id": inv["id"],
                "amount": "100.00",
                "payment_date": "2026-07-02",
            },
        )
        assert blocked.status_code == 400

        sent = await client.patch(
            f"/api/billing/invoices/{inv['id']}", json={"status": "sent"}
        )
        assert sent.status_code == 200, sent.text
        assert sent.json()["sent_at"] is not None

        pay = await client.post(
            "/api/billing/payments",
            json={
                "invoice_id": inv["id"],
                "amount": "100.00",
                "payment_date": "2026-07-02",
                "method": "check",
            },
        )
        assert pay.status_code == 201, pay.text

        detail = (await client.get(f"/api/billing/invoices/{inv['id']}")).json()
        assert detail["status"] == "partially_paid"
        assert Decimal(detail["amount_paid"]) == Decimal("100.00")
        assert Decimal(detail["balance_due"]) == Decimal(inv["total"]) - Decimal(
            "100.00"
        )

    async def test_void_releases_time_entries(self, client, test_matter):
        entry = await _log_time(client, test_matter.id)
        inv = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()

        billed = (await client.get(f"/api/billing/time-entries/{entry['id']}")).json()
        assert billed["status"] == "invoiced"
        assert billed["invoice_id"] == inv["id"]

        void = await client.patch(
            f"/api/billing/invoices/{inv['id']}", json={"status": "void"}
        )
        assert void.status_code == 200, void.text

        released = (await client.get(f"/api/billing/time-entries/{entry['id']}")).json()
        assert released["status"] == "draft"
        assert released["invoice_id"] is None

        # Released time can be re-invoiced
        resp = await client.post(
            "/api/billing/invoices/generate",
            json={"matter_id": str(test_matter.id)},
        )
        assert resp.status_code == 201

    async def test_cannot_void_paid_invoice(self, client, test_matter):
        await _log_time(client, test_matter.id)
        inv = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()
        await client.patch(
            f"/api/billing/invoices/{inv['id']}", json={"status": "sent"}
        )
        await client.post(
            "/api/billing/payments",
            json={
                "invoice_id": inv["id"],
                "amount": inv["total"],
                "payment_date": "2026-07-02",
            },
        )
        resp = await client.patch(
            f"/api/billing/invoices/{inv['id']}", json={"status": "void"}
        )
        assert resp.status_code == 400


class TestTimeEntryFilters:
    async def test_nonbillable_entry_records_zero_even_when_matter_has_a_rate(
        self, client, test_matter
    ):
        response = await client.post(
            "/api/billing/time-entries",
            json={
                "matter_id": str(test_matter.id),
                "description": "Internal team meeting",
                "hours": "0.5",
                "date": "2026-07-01",
                "is_billable": False,
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["hourly_rate"] == "0.00"
        assert response.json()["amount"] == "0.00"

    async def test_date_filters_and_pagination_totals(self, client, test_matter):
        for day, hours in (("2026-06-01", "1.0"), ("2026-07-01", "2.0")):
            resp = await client.post(
                "/api/billing/time-entries",
                json={
                    "matter_id": str(test_matter.id),
                    "description": "Work",
                    "hours": hours,
                    "date": day,
                },
            )
            assert resp.status_code == 201

        july = await client.get(
            "/api/billing/time-entries", params={"date_from": "2026-07-01"}
        )
        data = july.json()
        assert data["total"] == 1
        assert Decimal(data["total_hours"]) == Decimal("2.0")

        # Totals cover the filtered set even when the page is smaller
        paged = await client.get("/api/billing/time-entries", params={"limit": 1})
        pdata = paged.json()
        assert len(pdata["items"]) == 1
        assert pdata["total"] == 2
        assert Decimal(pdata["total_hours"]) == Decimal("3.0")


class TestMatterExpenses:
    async def test_internal_expense_is_recorded_but_never_enters_prebill(
        self, client, test_matter
    ):
        created = await client.post(
            "/api/billing/expenses",
            json={
                "matter_id": str(test_matter.id),
                "description": "Team lunch to discuss case strategy",
                "amount": "74.50",
                "date": "2026-08-25",
                "category": "meals",
                "vendor": "Main Street Cafe",
                "reference_number": "RCPT-8821",
                # The server enforces the internal-only category even if a
                # caller mistakenly asks to pass it through to the client.
                "is_billable": True,
                "payment_method": "firm_card",
                "payment_account": "Firm Amex",
                "expense_account": "Meals and entertainment",
                "tax_amount": "5.25",
                "notes": "Internal strategy meeting; never show on client invoice.",
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["is_billable"] is False
        assert body["review_status"] == "ready"
        assert body["reference_number"] == "RCPT-8821"
        assert body["qbo_payment_account_name"] == "Firm Amex"
        assert body["qbo_expense_account_name"] == "Meals and entertainment"

        preview = await client.get(
            "/api/billing/invoices/preview",
            params={"matter_id": str(test_matter.id)},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["expenses"] == []

        ledger = await client.get(
            "/api/billing/expenses", params={"matter_id": str(test_matter.id)}
        )
        assert ledger.status_code == 200, ledger.text
        assert ledger.json()["total"] == 1
        assert Decimal(ledger.json()["total_amount"]) == Decimal("74.50")

    async def test_client_amount_is_distinct_from_cost_and_drives_invoice(
        self, client, test_matter
    ):
        created = await client.post(
            "/api/billing/expenses",
            json={
                "matter_id": str(test_matter.id),
                "description": "Service of process",
                "amount": "100.00",
                "client_amount": "125.00",
                "date": "2026-08-25",
                "category": "process service",
                "vendor": "County Process LLC",
                "is_billable": True,
            },
        )
        assert created.status_code == 201, created.text
        expense = created.json()

        preview = await client.get(
            "/api/billing/invoices/preview",
            params={"matter_id": str(test_matter.id)},
        )
        assert preview.status_code == 200, preview.text
        row = preview.json()["expenses"][0]
        assert Decimal(row["cost_amount"]) == Decimal("100.00")
        assert Decimal(row["amount"]) == Decimal("125.00")
        assert Decimal(preview.json()["expense_amount"]) == Decimal("125.00")

        invoice = await client.post(
            "/api/billing/invoices/generate",
            json={
                "matter_id": str(test_matter.id),
                "time_entry_ids": [],
                "expense_ids": [expense["id"]],
            },
        )
        assert invoice.status_code == 201, invoice.text
        assert Decimal(invoice.json()["subtotal"]) == Decimal("125.00")
        assert Decimal(invoice.json()["line_items"][0]["amount"]) == Decimal(
            "125.00"
        )

    async def test_receipt_review_state_gates_prebill(self, client, test_matter):
        created = (
            await client.post(
                "/api/billing/expenses",
                json={
                    "matter_id": str(test_matter.id),
                    "description": "Court filing fee",
                    "amount": "85.00",
                    "date": "2026-08-25",
                    "category": "court filing",
                    "is_billable": True,
                },
            )
        ).json()
        pending = await client.patch(
            f"/api/billing/expenses/{created['id']}",
            json={"review_status": "needs_review"},
        )
        assert pending.status_code == 200, pending.text

        preview = await client.get(
            "/api/billing/invoices/preview",
            params={"matter_id": str(test_matter.id)},
        )
        assert preview.json()["expenses"] == []

        approved = await client.patch(
            f"/api/billing/expenses/{created['id']}",
            json={"review_status": "approved"},
        )
        assert approved.status_code == 200, approved.text
        preview = await client.get(
            "/api/billing/invoices/preview",
            params={"matter_id": str(test_matter.id)},
        )
        assert [item["id"] for item in preview.json()["expenses"]] == [created["id"]]


class TestBillingSettings:
    async def test_settings_roundtrip_and_timer_rounding(self, client, test_matter):
        # Defaults
        resp = await client.get("/api/billing/settings")
        assert resp.status_code == 200
        assert resp.json()["time_rounding_minutes"] == 6

        # Update to quarter-hour rounding
        put = await client.put(
            "/api/billing/settings",
            json={"time_rounding_minutes": 15, "default_hourly_rate": "300"},
        )
        assert put.status_code == 200, put.text
        body = put.json()
        assert body["time_rounding_minutes"] == 15
        assert Decimal(body["default_hourly_rate"]) == Decimal("300")

        # Timer now bills a minimum of 0.25h
        await client.post(
            "/api/billing/time-entries/timer/start",
            json={"matter_id": str(test_matter.id)},
        )
        stop = await client.post("/api/billing/time-entries/timer/stop", json={})
        assert Decimal(stop.json()["hours"]) == Decimal("0.25")


@pytest.mark.asyncio
async def test_timer_start_accepts_the_timekeepers_local_date(client, test_matter):
    """An evening entry must not be stamped with tomorrow's UTC date."""
    matter = test_matter

    local_day = (date.today() - timedelta(days=1)).isoformat()
    r = await client.post(
        "/api/billing/time-entries/timer/start",
        json={
            "matter_id": str(matter.id),
            "description": "Evening call",
            "date": local_day,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["date"] == local_day

    await client.delete("/api/billing/time-entries/timer")


@pytest.mark.asyncio
async def test_timer_stop_records_the_narrative(client, test_matter):
    """The description given at stop is what lands on the bill."""
    matter = test_matter

    start = await client.post(
        "/api/billing/time-entries/timer/start",
        json={"matter_id": str(matter.id)},
    )
    assert start.status_code == 201, start.text

    stop = await client.post(
        "/api/billing/time-entries/timer/stop",
        json={"description": "Call with opposing counsel"},
    )
    assert stop.status_code == 200, stop.text
    assert stop.json()["description"] == "Call with opposing counsel"
    assert stop.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_time_entry_list_names_the_timekeeper(client, test_matter, test_user):
    """A firm-wide list is unreadable without who recorded each entry."""
    matter = test_matter

    created = await client.post(
        "/api/billing/time-entries",
        json={
            "matter_id": str(matter.id),
            "description": "Drafted motion",
            "hours": "1.5",
            "hourly_rate": "200.00",
            "date": date.today().isoformat(),
        },
    )
    assert created.status_code == 201, created.text

    listing = await client.get(f"/api/billing/time-entries?matter_id={matter.id}")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert items
    assert items[0]["user_name"] == test_user.full_name


@pytest.mark.asyncio
async def test_time_entry_settings_readable_without_finance_access(
    db_session, test_tenant, test_redis
):
    """Every timekeeper needs the increment; only finance sees firm rates."""
    from datetime import datetime, timezone

    from httpx import ASGITransport, AsyncClient
    from jose import jwt as jose_jwt

    from app.config import get_settings
    from app.database import get_db
    from app.main import app
    from app.models.user import User

    settings = get_settings()
    timekeeper = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="paralegal@testfirm.com",
        full_name="Pat Paralegal",
        role="user",
        oauth_provider="google",
        oauth_subject="google-sub-paralegal",
        is_active=True,
    )
    db_session.add(timekeeper)
    await db_session.commit()

    token = jose_jwt.encode(
        {
            "sub": str(timekeeper.id),
            "tenant_id": str(test_tenant.id),
            "role": timekeeper.role,
            "email": timekeeper.email,
            "billing_tier": test_tenant.billing_tier,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    previous_redis = getattr(app.state, "redis", None)
    app.state.redis = test_redis
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as ac:
            allowed = await ac.get("/api/billing/time-entry-settings")
            assert allowed.status_code == 200
            assert allowed.json()["time_rounding_minutes"] == 6

            # The firm's rates stay behind the finance gate.
            refused = await ac.get("/api/billing/settings")
            assert refused.status_code == 403
    finally:
        app.state.redis = previous_redis
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_time_entry_date_can_be_corrected(client, test_matter):
    """Editing an entry's date must work: the edit form sends it on every save."""
    created = await client.post(
        "/api/billing/time-entries",
        json={
            "matter_id": str(test_matter.id),
            "description": "Drafted motion",
            "hours": "1.0",
            "date": "2026-07-01",
        },
    )
    assert created.status_code == 201, created.text

    corrected = await client.patch(
        f"/api/billing/time-entries/{created.json()['id']}",
        json={"description": "Drafted motion", "hours": "1.0", "date": "2026-06-30"},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["date"] == "2026-06-30"


@pytest.mark.asyncio
async def test_expense_date_can_be_corrected(client, test_matter):
    """Same for expenses: a mis-dated receipt has to be fixable."""
    created = await client.post(
        "/api/billing/expenses",
        json={
            "matter_id": str(test_matter.id),
            "description": "Filing fee",
            "amount": "125.00",
            "date": "2026-07-01",
        },
    )
    assert created.status_code == 201, created.text

    corrected = await client.patch(
        f"/api/billing/expenses/{created.json()['id']}",
        json={"date": "2026-06-30"},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["date"] == "2026-06-30"


class TestDraftLineItemEditing:
    """The bill review loop: adjust a generated draft before the client sees it."""

    async def test_reword_and_write_down_a_line(self, client, test_matter):
        await _log_time(client, test_matter.id, hours="4.0")
        invoice = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()
        line = invoice["line_items"][0]
        assert Decimal(invoice["total"]) == Decimal("1000.00")

        edited = await client.patch(
            f"/api/billing/invoices/{invoice['id']}/line-items/{line['id']}",
            json={"description": "Drafted and revised motion", "unit_price": "200.00"},
        )
        assert edited.status_code == 200, edited.text
        body = edited.json()
        assert body["line_items"][0]["description"] == "Drafted and revised motion"
        # 4 hours written down from $250 to $200 an hour.
        assert Decimal(body["line_items"][0]["amount"]) == Decimal("800.00")
        assert Decimal(body["subtotal"]) == Decimal("800.00")
        assert Decimal(body["total"]) == Decimal("800.00")

    async def test_add_a_discount_line(self, client, test_matter):
        await _log_time(client, test_matter.id, hours="4.0")
        invoice = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()

        discounted = await client.post(
            f"/api/billing/invoices/{invoice['id']}/line-items",
            json={
                "description": "Courtesy discount",
                "amount": "100.00",
                "source_type": "discount",
            },
        )
        assert discounted.status_code == 201, discounted.text
        body = discounted.json()
        # A discount is stored negative so the subtotal simply sums.
        assert Decimal(body["line_items"][-1]["amount"]) == Decimal("-100.00")
        assert Decimal(body["total"]) == Decimal("900.00")

    async def test_add_a_flat_fee_line(self, client, test_matter):
        await _log_time(client, test_matter.id, hours="1.0")
        invoice = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()

        added = await client.post(
            f"/api/billing/invoices/{invoice['id']}/line-items",
            json={
                "description": "Filing package",
                "amount": "500.00",
                "source_type": "flat_fee",
            },
        )
        assert added.status_code == 201, added.text
        assert Decimal(added.json()["total"]) == Decimal("750.00")

    async def test_removing_a_line_releases_the_work(self, client, test_matter):
        entry = await _log_time(client, test_matter.id, hours="2.0")
        invoice = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()
        line = invoice["line_items"][0]

        removed = await client.delete(
            f"/api/billing/invoices/{invoice['id']}/line-items/{line['id']}"
        )
        assert removed.status_code == 200, removed.text
        assert removed.json()["line_items"] == []
        assert Decimal(removed.json()["total"]) == Decimal("0.00")

        # The hours must return to the unbilled pool, not be stranded.
        released = await client.get(f"/api/billing/time-entries/{entry['id']}")
        assert released.status_code == 200
        assert released.json()["invoice_id"] is None
        assert released.json()["status"] == "draft"

    async def test_sent_invoices_are_not_editable(self, client, test_matter):
        await _log_time(client, test_matter.id, hours="1.0")
        invoice = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()
        sent = await client.patch(
            f"/api/billing/invoices/{invoice['id']}", json={"status": "sent"}
        )
        assert sent.status_code == 200, sent.text

        refused = await client.patch(
            f"/api/billing/invoices/{invoice['id']}/line-items/{invoice['line_items'][0]['id']}",
            json={"description": "Too late"},
        )
        assert refused.status_code == 400
        assert "draft" in refused.json()["detail"].lower()

    async def test_a_zero_amount_adjustment_is_refused(self, client, test_matter):
        await _log_time(client, test_matter.id, hours="1.0")
        invoice = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()
        refused = await client.post(
            f"/api/billing/invoices/{invoice['id']}/line-items",
            json={"description": "Nothing", "amount": "0"},
        )
        assert refused.status_code == 422


class TestInvoiceDelivery:
    async def test_send_reports_unconfigured_email_without_marking_sent(
        self, client, test_matter, db_session, test_tenant
    ):
        """A bill that never left the building must not become outstanding A/R."""
        from app.models.contact import Contact

        client_contact = Contact(
            id=uuid.uuid4(),
            tenant_id=test_tenant.id,
            first_name="Client",
            last_name="Contact",
            email="client@example.com",
        )
        db_session.add(client_contact)
        await db_session.commit()

        matter_result = await db_session.execute(
            select(Matter).where(Matter.id == test_matter.id)
        )
        matter = matter_result.scalar_one()
        matter.client_contact_id = client_contact.id
        await db_session.commit()

        await _log_time(client, test_matter.id, hours="1.0")
        invoice = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()

        sent = await client.post(
            f"/api/billing/invoices/{invoice['id']}/send", json={}
        )
        assert sent.status_code == 200, sent.text
        body = sent.json()
        # Email is not configured in tests, so delivery must report failure
        # and the invoice must stay a draft.
        assert body["delivered"] is False
        assert body["recipients"] == ["client@example.com"]
        assert body["invoice"]["status"] == "draft"
        assert body["invoice"]["sent_at"] is None

    async def test_send_requires_a_recipient(self, client, test_matter):
        await _log_time(client, test_matter.id, hours="1.0")
        invoice = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()

        refused = await client.post(
            f"/api/billing/invoices/{invoice['id']}/send", json={}
        )
        assert refused.status_code == 400
        assert "recipient" in refused.json()["detail"].lower()


class TestTrustApplication:
    """Applying client funds already held is the defining legal-billing move."""

    async def _retainer(self, db_session, tenant_id, matter_id, user_id, amount):
        from app.models.contact import Contact
        from app.models.retainer import Retainer

        contact = Contact(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            first_name="Trust",
            last_name="Client",
            email="trust@example.com",
        )
        db_session.add(contact)
        await db_session.commit()

        retainer = Retainer(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            matter_id=matter_id,
            contact_id=contact.id,
            retainer_type="evergreen",
            amount=Decimal(amount),
            current_balance=Decimal(amount),
            minimum_balance=Decimal("500.00"),
            status="active",
        )
        db_session.add(retainer)
        await db_session.commit()
        await db_session.refresh(retainer)
        return retainer

    async def _sent_invoice(self, client, matter_id, hours="4.0"):
        await _log_time(client, matter_id, hours=hours)
        invoice = (
            await client.post(
                "/api/billing/invoices/generate", json={"matter_id": str(matter_id)}
            )
        ).json()
        await client.patch(
            f"/api/billing/invoices/{invoice['id']}", json={"status": "sent"}
        )
        return invoice

    async def test_applying_trust_moves_both_ledgers_together(
        self, client, db_session, test_tenant, test_user, test_matter
    ):
        from app.models.retainer import Retainer

        retainer = await self._retainer(
            db_session, test_tenant.id, test_matter.id, test_user.id, "2000.00"
        )
        invoice = await self._sent_invoice(client, test_matter.id)

        # Snapshot the id: the session is expired below, and touching an
        # expired ORM attribute afterwards triggers a sync refresh.
        retainer_id = retainer.id

        applied = await client.post(
            f"/api/billing/invoices/{invoice['id']}/apply-trust",
            json={"retainer_id": str(retainer_id), "amount": "400.00"},
        )
        assert applied.status_code == 201, applied.text
        body = applied.json()

        # The invoice records the payment...
        assert Decimal(body["amount_paid"]) == Decimal("400.00")
        assert body["status"] == "partially_paid"
        assert body["payments"][0]["method"] == "trust"

        # ...and the retainer balance actually moved. Without this the two
        # ledgers drift: the old drawdown route never wrote a payment, and the
        # payment route never touched the retainer.
        db_session.expire_all()
        balance = await db_session.scalar(
            select(Retainer.current_balance).where(Retainer.id == retainer_id)
        )
        assert balance == Decimal("1600.00")

    async def test_applying_trust_defaults_to_settling_the_bill(
        self, client, db_session, test_tenant, test_user, test_matter
    ):
        retainer = await self._retainer(
            db_session, test_tenant.id, test_matter.id, test_user.id, "5000.00"
        )
        invoice = await self._sent_invoice(client, test_matter.id)

        applied = await client.post(
            f"/api/billing/invoices/{invoice['id']}/apply-trust",
            json={"retainer_id": str(retainer.id)},
        )
        assert applied.status_code == 201, applied.text
        assert applied.json()["status"] == "paid"
        assert Decimal(applied.json()["balance_due"]) == Decimal("0.00")

    async def test_cannot_overdraw_the_retainer(
        self, client, db_session, test_tenant, test_user, test_matter
    ):
        retainer = await self._retainer(
            db_session, test_tenant.id, test_matter.id, test_user.id, "100.00"
        )
        invoice = await self._sent_invoice(client, test_matter.id)

        refused = await client.post(
            f"/api/billing/invoices/{invoice['id']}/apply-trust",
            json={"retainer_id": str(retainer.id), "amount": "500.00"},
        )
        assert refused.status_code == 400
        assert "insufficient" in refused.json()["detail"].lower()

    async def test_cannot_apply_trust_to_a_draft(
        self, client, db_session, test_tenant, test_user, test_matter
    ):
        retainer = await self._retainer(
            db_session, test_tenant.id, test_matter.id, test_user.id, "2000.00"
        )
        await _log_time(client, test_matter.id, hours="1.0")
        invoice = (
            await client.post(
                "/api/billing/invoices/generate",
                json={"matter_id": str(test_matter.id)},
            )
        ).json()

        refused = await client.post(
            f"/api/billing/invoices/{invoice['id']}/apply-trust",
            json={"retainer_id": str(retainer.id)},
        )
        assert refused.status_code == 400

    async def test_available_trust_flags_an_evergreen_shortfall(
        self, client, db_session, test_tenant, test_user, test_matter
    ):
        retainer = await self._retainer(
            db_session, test_tenant.id, test_matter.id, test_user.id, "2000.00"
        )
        retainer_id = retainer.id
        invoice = await self._sent_invoice(client, test_matter.id, hours="8.0")

        # Draw the balance under its evergreen floor of $500.
        drawn = await client.post(
            f"/api/billing/invoices/{invoice['id']}/apply-trust",
            json={"retainer_id": str(retainer_id), "amount": "1600.00"},
        )
        assert drawn.status_code == 201, drawn.text
        db_session.expire_all()

        available = await client.get(
            f"/api/billing/invoices/{invoice['id']}/available-trust"
        )
        assert available.status_code == 200, available.text
        row = next(r for r in available.json() if r["retainer_id"] == str(retainer_id))
        assert Decimal(row["current_balance"]) == Decimal("400.00")
        assert row["needs_replenishment"] is True


class TestFeeParity:
    async def test_fixed_fee_without_dummy_time_and_explicit_dates(self, client, test_matter):
        response = await client.post("/api/billing/invoices/generate", json={
            "matter_id": str(test_matter.id), "issue_date": "2025-12-31",
            "due_date": "2026-01-15", "date_to": "2025-12-30", "tax_rate": "0.05",
            "manual_charges": [{"description": "Estate package", "quantity": "2", "unit_price": "1250.00"}],
        })
        assert response.status_code == 201, response.text
        invoice = response.json()
        assert invoice["invoice_number"].startswith("INV-2025-")
        assert invoice["status"] == "draft"
        assert Decimal(invoice["total"]) == Decimal("2625.00")
        assert invoice["due_date"] == "2026-01-15"
        assert invoice["billing_details"]["work_through"] == "2025-12-30"
        assert invoice["line_items"][0]["source_type"] == "flat_fee"
        assert invoice["line_items"][0]["source_id"] is None

    async def test_stage_selection_replay_and_void(self, client, test_matter):
        response = await client.post("/api/billing/fees", json={
            "matter_id": str(test_matter.id), "description": "Filing stage",
            "amount": "1800.00", "service_date": "2026-09-01",
        })
        assert response.status_code == 201, response.text
        fee = response.json()
        preview_url = "/api/billing/invoices/preview"
        params = {"matter_id": str(test_matter.id)}
        assert (await client.get(preview_url, params=params)).json()["fees"] == []
        ready = await client.patch(f"/api/billing/fees/{fee['id']}", json={"status": "ready"})
        assert ready.status_code == 200
        assert len((await client.get(preview_url, params=params)).json()["fees"]) == 1
        payload = {"matter_id": str(test_matter.id), "fee_ids": [fee["id"]]}
        invoice_response = await client.post("/api/billing/invoices/generate", json=payload)
        assert invoice_response.status_code == 201, invoice_response.text
        invoice = invoice_response.json()
        assert Decimal(invoice["total"]) == Decimal("1800")
        assert (await client.post("/api/billing/invoices/generate", json=payload)).status_code == 409
        assert (await client.patch(f"/api/billing/fees/{fee['id']}", json={"status": "ready"})).status_code == 409
        assert (await client.patch(f"/api/billing/invoices/{invoice['id']}", json={"status": "void"})).status_code == 200
        assert len((await client.get(preview_url, params=params)).json()["fees"]) == 1

    async def test_invalid_manual_charge_and_due_date(self, client, test_matter):
        base = {"matter_id": str(test_matter.id), "manual_charges": [{"description": "Fee", "unit_price": "25"}]}
        response = await client.post("/api/billing/invoices/generate", json={**base, "issue_date": "2026-10-01", "due_date": "2026-09-30"})
        assert response.status_code == 400
        base["manual_charges"][0]["description"] = "   "
        assert (await client.post("/api/billing/invoices/generate", json=base)).status_code == 422


class TestScheduledBillingParity:
    async def test_opt_in_calendar_drafts_and_pause(self, client, test_matter, db_session, test_tenant):
        from app.models.billing import Invoice
        from app.services.scheduled_billing import run_schedules
        response = await client.post("/api/billing/schedules", json={
            "matter_id": str(test_matter.id), "first_invoice_date": date.today().isoformat(),
            "fixed_description": "Monthly advisory", "fixed_amount": "750.00",
            "include_unbilled_work": False,
        })
        assert response.status_code == 201, response.text
        schedule = response.json()
        tenant_id = test_tenant.id
        await run_schedules(db_session, tenant_id)
        invoices = (await db_session.execute(select(Invoice).where(Invoice.tenant_id == tenant_id))).scalars().all()
        assert len(invoices) == 1
        assert invoices[0].status == "draft"
        assert invoices[0].total == Decimal("750")
        await run_schedules(db_session, tenant_id)
        assert len((await db_session.execute(select(Invoice).where(Invoice.tenant_id == tenant_id))).scalars().all()) == 1
        paused = await client.patch(f"/api/billing/schedules/{schedule['id']}", json={"paused": True})
        assert paused.status_code == 200 and paused.json()["paused"]

    async def test_generation_key_reuses_same_draft_and_rejects_different_content(self, client, test_matter):
        payload = {"matter_id": str(test_matter.id), "generation_key": str(uuid.uuid4()),
            "manual_charges": [{"description": "Fee", "unit_price": "500"}]}
        first = await client.post("/api/billing/invoices/generate", json=payload)
        assert first.status_code == 201, first.text
        again = await client.post("/api/billing/invoices/generate", json=payload)
        assert again.status_code == 201, again.text
        assert first.json()["id"] == again.json()["id"]
        payload["manual_charges"][0]["unit_price"] = "600"
        assert (await client.post("/api/billing/invoices/generate", json=payload)).status_code == 409

    async def test_fixed_fee_qbo_export_and_existing_invoice_update(self, client, test_matter, db_session, test_tenant, monkeypatch):
        from app.services.qbo_sync import QBOSyncService
        from app.models.qbo import QBOItemMapping
        response = await client.post("/api/billing/invoices/generate", json={"matter_id": str(test_matter.id),
            "issue_date": "2026-08-31", "due_date": "2026-09-15",
            "manual_charges": [{"description": "Fixed service", "unit_price": "500"}]})
        assert response.status_code == 201, response.text
        invoice_id = response.json()["id"]
        db_session.add(QBOItemMapping(tenant_id=test_tenant.id, source_type="flat_fee", qbo_item_id="22", qbo_item_name="Fixed legal service"))
        await db_session.commit()
        service = QBOSyncService(db_session, str(test_tenant.id), "synthetic-token")
        from unittest.mock import AsyncMock
        monkeypatch.setattr(service, "_get_realm_id", AsyncMock(return_value="test-realm"))
        monkeypatch.setattr(service, "_ensure_customer", AsyncMock(return_value={"Id": "customer"}))
        request = AsyncMock(return_value={"Invoice": {"Id": "qbo-invoice", "SyncToken": "1"}})
        monkeypatch.setattr(service, "_request", request)
        assert await service.sync_invoice_with_retry(invoice_id) is None
        request.assert_not_called()
        marked = await client.patch(f"/api/billing/invoices/{invoice_id}", json={"status": "sent"})
        assert marked.status_code == 200
        await service.sync_invoice(invoice_id)
        payload = request.call_args.kwargs["json_data"]
        assert payload["TxnDate"] == "2026-08-31"
        assert payload["DueDate"] == "2026-09-15"
        assert payload["Line"][0]["Amount"] == 500
        assert payload["Line"][0]["SalesItemLineDetail"]["ItemRef"]["value"] == "22"
        await service.sync_invoice(invoice_id)
        assert request.call_args.kwargs["json_data"]["Id"] == "qbo-invoice"
        assert request.call_args.kwargs["json_data"]["SyncToken"] == "1"


class TestBillingCollectionsParity:
    async def test_payment_plan_matches_total_and_is_cleared_by_draft_adjustment(self, client, test_matter):
        created = await client.post("/api/billing/invoices/generate", json={"matter_id": str(test_matter.id),
            "issue_date": "2026-09-01", "manual_charges": [{"description": "Work", "unit_price": "600"}]})
        invoice = created.json()
        url = f"/api/billing/invoices/{invoice['id']}/payment-plan"
        rows = [{"due_date": "2026-09-15", "amount": "300"}, {"due_date": "2026-10-15", "amount": "300"}]
        assert (await client.put(url, json={"installments": rows[:1]})).status_code == 400
        plan = await client.put(url, json={"installments": rows})
        assert plan.status_code == 200, plan.text
        assert len(plan.json()["billing_details"]["installments"]) == 2
        changed = await client.post(f"/api/billing/invoices/{invoice['id']}/line-items", json={"source_type": "flat_fee", "description": "Extra", "amount": "50"})
        assert changed.status_code == 201, changed.text
        assert "installments" not in changed.json()["billing_details"]

    async def test_ready_to_bill_finds_closed_matters_and_ready_fees(self, client, test_matter, db_session):
        matter_id = str(test_matter.id)
        test_matter.is_closed = True
        await db_session.commit()
        fee = await client.post("/api/billing/fees", json={"matter_id": matter_id, "description": "Final stage", "amount": "450", "service_date": "2026-09-01", "ready": True})
        assert fee.status_code == 201
        ready = await client.get("/api/billing/ready-to-bill", params={"date_to": "2026-09-30", "q": "Smith"})
        assert ready.status_code == 200, ready.text
        assert ready.json()["total"] == 1
        assert ready.json()["items"][0]["count"] == 1
        assert ready.json()["items"][0]["closed"] is True
        assert Decimal(ready.json()["total_amount"]) == Decimal("450")


class TestBillingParityBoundaries:
    @pytest.mark.parametrize("changes,status", [
        ({"timezone": "Missing/Zone"}, 422),
        ({"end_date": "2020-01-01"}, 400),
        ({"fixed_amount": "50", "fixed_description": " "}, 400),
        ({"include_unbilled_work": False}, 400),
    ])
    async def test_rejects_invalid_schedule(self, client, test_matter, changes, status):
        response = await client.post("/api/billing/schedules", json={"matter_id": str(test_matter.id), "first_invoice_date": date.today().isoformat(), **changes})
        assert response.status_code == status, response.text

    async def test_schedule_unique_and_pause_resume_visible(self, client, test_matter):
        payload = {"matter_id": str(test_matter.id), "first_invoice_date": date.today().isoformat()}
        created = await client.post("/api/billing/schedules", json=payload)
        assert created.status_code == 201
        assert (await client.post("/api/billing/schedules", json=payload)).status_code == 409
        url = f"/api/billing/schedules/{created.json()['id']}"
        for paused in [True, False]:
            assert (await client.patch(url, json={"paused": paused})).json()["paused"] is paused
        listed = await client.get("/api/billing/schedules", params={"matter_id": payload["matter_id"]})
        assert len(listed.json()["items"]) == 1
        assert (await client.patch(f"/api/billing/schedules/{uuid.uuid4()}", json={"paused": True})).status_code == 404

    @pytest.mark.parametrize("reason", ["closed", "pro_bono"])
    async def test_schedule_cannot_start_or_continue_for_nonbillable_matter(self, client, test_matter, test_tenant, db_session, reason):
        from app.models.billing import BillingSchedule, Invoice
        from app.services.scheduled_billing import run_schedules
        tenant_id, matter_id = test_tenant.id, test_matter.id
        created = await client.post("/api/billing/schedules", json={"matter_id": str(matter_id), "first_invoice_date": date.today().isoformat()})
        assert created.status_code == 201
        if reason == "closed":
            test_matter.is_closed = True
        else:
            test_matter.billing_method = "pro_bono"
        await db_session.commit()
        rejected = await client.post("/api/billing/schedules", json={"matter_id": str(matter_id), "first_invoice_date": date.today().isoformat()})
        assert rejected.status_code == 400
        await run_schedules(db_session, tenant_id)
        schedule = await db_session.scalar(select(BillingSchedule).where(BillingSchedule.matter_id == matter_id))
        assert schedule.paused and schedule.last_error
        assert await db_session.scalar(select(Invoice.id).where(Invoice.matter_id == matter_id)) is None

    async def test_empty_scheduled_period_advances_without_phantom_invoice(self, client, test_matter, test_tenant, db_session):
        from app.models.billing import BillingSchedule, Invoice
        from app.services.scheduled_billing import run_schedules
        tenant_id, matter_id = test_tenant.id, test_matter.id
        await client.post("/api/billing/schedules", json={"matter_id": str(matter_id), "first_invoice_date": date.today().isoformat()})
        await run_schedules(db_session, tenant_id)
        schedule = await db_session.scalar(select(BillingSchedule).where(BillingSchedule.matter_id == matter_id))
        assert schedule.next_date > date.today()
        assert await db_session.scalar(select(Invoice.id).where(Invoice.matter_id == matter_id)) is None

    @pytest.mark.parametrize("error_kind", ["http", "provider"])
    async def test_failed_schedule_keeps_date_for_retry(self, client, test_matter, test_tenant, db_session, monkeypatch, error_kind):
        from unittest.mock import AsyncMock
        from fastapi import HTTPException
        from app.models.billing import BillingSchedule
        from app.services.scheduled_billing import run_schedules
        tenant_id, matter_id = test_tenant.id, test_matter.id
        await client.post("/api/billing/schedules", json={"matter_id": str(matter_id), "first_invoice_date": date.today().isoformat()})
        error = HTTPException(409, "conflict") if error_kind == "http" else RuntimeError("synthetic failure")
        monkeypatch.setattr("app.routers.billing_extended._generate_invoice", AsyncMock(side_effect=error))
        await run_schedules(db_session, tenant_id)
        schedule = await db_session.scalar(select(BillingSchedule).where(BillingSchedule.matter_id == matter_id))
        assert schedule.next_date == date.today()
        assert schedule.last_error

    async def test_cancelled_fee_and_invalid_fee_state(self, client, test_matter):
        response = await client.post("/api/billing/fees", json={"matter_id": str(test_matter.id), "description": "Milestone", "amount": "200", "service_date": "2026-09-01"})
        fee = response.json()
        url = f"/api/billing/fees/{fee['id']}"
        assert (await client.patch(url, json={"status": "paid"})).status_code == 422
        assert (await client.patch(url, json={"status": "cancelled"})).status_code == 200
        assert (await client.patch(url, json={"status": "ready"})).status_code == 409
        listed = await client.get("/api/billing/fees", params={"matter_id": str(test_matter.id)})
        assert listed.json()["items"][0]["status"] == "cancelled"
        assert (await client.patch(f"/api/billing/fees/{uuid.uuid4()}", json={"status": "ready"})).status_code == 404

    async def test_payment_plan_dates_and_overdue_after_partial_payment(self, client, test_matter):
        created = await client.post("/api/billing/invoices/generate", json={"matter_id": str(test_matter.id), "issue_date": "2026-01-01", "due_date": "2026-01-31", "manual_charges": [{"description": "Work", "unit_price": "200"}]})
        invoice_id = created.json()["id"]
        url = f"/api/billing/invoices/{invoice_id}/payment-plan"
        assert (await client.put(url, json={"installments": [{"due_date": "2025-12-31", "amount": "200"}]})).status_code == 400
        assert (await client.put(url, json={"installments": [{"due_date": "2026-01-31", "amount": "100"}]*2})).status_code == 400
        rows = [{"due_date": "2026-01-31", "amount": "100"}, {"due_date": "2099-01-01", "amount": "100"}]
        assert (await client.put(url, json={"installments": rows})).status_code == 200
        await client.patch(f"/api/billing/invoices/{invoice_id}", json={"status": "sent"})
        assert (await client.get(f"/api/billing/invoices/{invoice_id}")).json()["is_overdue"]
        paid = await client.post("/api/billing/payments", json={"invoice_id": invoice_id, "amount": "100", "method": "check", "payment_date": date.today().isoformat()})
        assert paid.status_code == 201, paid.text
        assert not (await client.get(f"/api/billing/invoices/{invoice_id}")).json()["is_overdue"]
        assert not (await client.get("/api/billing/invoices", params={"overdue_only": True})).json()["items"]
        assert (await client.put(url, json={"installments": rows})).status_code == 409


@pytest.mark.parametrize("source", ["time", "fee"])
async def test_concurrent_drafts_cannot_claim_same_source(client, test_matter, test_user, test_tenant, test_engine, db_session, source):
    import asyncio
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.billing import Invoice, InvoiceLineItem
    from app.models.user import User
    from app.routers.billing_extended import _generate_invoice
    from app.schemas.billing import GenerateInvoiceRequest
    tenant_id, user_id, matter_id = test_tenant.id, test_user.id, test_matter.id
    payload = {"matter_id": str(matter_id), "time_entry_ids": [], "expense_ids": []}
    if source == "time":
        entry = await _log_time(client, str(matter_id))
        source_id = entry["id"]
        payload["time_entry_ids"] = [source_id]
    else:
        fee = await client.post("/api/billing/fees", json={"matter_id": str(matter_id), "description": "Stage", "amount": "500", "service_date": "2026-09-01", "ready": True})
        source_id = fee.json()["id"]
        payload["fee_ids"] = [source_id]
    await db_session.commit()
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async def generate():
        async with factory() as session:
            user = await session.get(User, user_id)
            try:
                await _generate_invoice(GenerateInvoiceRequest(**payload), user, session)
                return 201
            except HTTPException as exc:
                await session.rollback()
                return exc.status_code
    assert sorted(await asyncio.gather(generate(), generate())) == [201, 409]
    invoices = (await db_session.execute(select(Invoice).where(Invoice.tenant_id == tenant_id))).scalars().all()
    assert len(invoices) == 1
    lines = (await db_session.execute(select(InvoiceLineItem).where(InvoiceLineItem.source_id == uuid.UUID(source_id)))).scalars().all()
    assert len(lines) == 1


async def test_installment_payment_link_collects_next_payment_and_retires_prior_link(client, test_matter, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.routers import billing_extended as billing
    import stripe
    monkeypatch.setattr(billing.settings, "STRIPE_SECRET_KEY", "sk_test_synthetic")
    price = Mock(return_value=SimpleNamespace(id="price-1"))
    links = Mock(side_effect=[SimpleNamespace(id="link-1", url="https://example.test/full"), SimpleNamespace(id="link-2", url="https://example.test/installment")])
    retire = Mock()
    monkeypatch.setattr(stripe.Price, "create", price)
    monkeypatch.setattr(stripe.PaymentLink, "create", links)
    monkeypatch.setattr(stripe.PaymentLink, "modify", retire)
    created = await client.post("/api/billing/invoices/generate", json={"matter_id": str(test_matter.id), "issue_date": "2026-01-01", "manual_charges": [{"description": "Work", "unit_price": "600"}]})
    invoice_id = created.json()["id"]
    await client.patch(f"/api/billing/invoices/{invoice_id}", json={"status": "sent"})
    link_url = f"/api/billing/invoices/{invoice_id}/payment-link"
    assert (await client.post(link_url)).status_code == 200
    assert price.call_args.kwargs["unit_amount"] == 60000
    plan = await client.put(f"/api/billing/invoices/{invoice_id}/payment-plan", json={"installments": [{"due_date": "2098-01-01", "amount": "200"}, {"due_date": "2099-01-01", "amount": "400"}]})
    assert plan.status_code == 200, plan.text
    retire.assert_called_once_with("link-1", active=False)
    assert (await client.post(link_url)).status_code == 200
    assert price.call_args.kwargs["unit_amount"] == 20000
    assert (await client.post(link_url)).status_code == 200
    assert price.call_count == 2


async def test_payment_plan_does_not_change_if_old_link_cannot_be_retired(client, test_matter, db_session, monkeypatch):
    from unittest.mock import Mock
    from app.models.billing import Invoice
    from app.routers import billing_extended as billing
    import stripe
    monkeypatch.setattr(billing.settings, "STRIPE_SECRET_KEY", "sk_test_synthetic")
    monkeypatch.setattr(stripe.PaymentLink, "modify", Mock(side_effect=stripe.StripeError("synthetic failure")))
    created = await client.post("/api/billing/invoices/generate", json={"matter_id": str(test_matter.id), "manual_charges": [{"description": "Work", "unit_price": "100"}]})
    invoice_id = uuid.UUID(created.json()["id"])
    invoice = await db_session.get(Invoice, invoice_id)
    invoice.stripe_payment_link = "https://example.test/full"
    invoice.stripe_payment_link_id = "existing-link"
    await db_session.commit()
    response = await client.put(f"/api/billing/invoices/{invoice_id}/payment-plan", json={"installments": [{"due_date": "2099-01-01", "amount": "100"}]})
    assert response.status_code == 502, response.text
    await db_session.refresh(invoice)
    assert "installments" not in invoice.billing_details
    assert invoice.stripe_payment_link_id == "existing-link"
