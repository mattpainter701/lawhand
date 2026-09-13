"""Age-based pruning of the operator diagnostic log tables."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.models.api_access_log import ApiAccessLog
from app.models.error_log import ErrorLog
from app.models.tenant import Tenant
from app.services import log_retention


def _ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@pytest.fixture
def retention_settings(monkeypatch):
    """Pin every retention knob so a deployment default cannot move a test."""

    settings = get_settings()
    monkeypatch.setattr(settings, "LOG_RETENTION_ENABLED", True)
    monkeypatch.setattr(settings, "ERROR_LOG_RETENTION_DAYS", 90)
    monkeypatch.setattr(settings, "API_ACCESS_LOG_RETENTION_DAYS", 30)
    monkeypatch.setattr(settings, "LOG_RETENTION_BATCH_SIZE", 5000)
    monkeypatch.setattr(settings, "LOG_RETENTION_MAX_BATCHES_PER_SCOPE", 40)
    return settings


@pytest.fixture
def bind_sweep(monkeypatch, test_engine):
    """Point the sweep's own session maker at the test database."""

    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(log_retention, "async_session_maker", factory)
    return factory


async def _seed(db_session, tenant: Tenant, *, error_ages, access_ages, system_ages=()):
    for age in error_ages:
        db_session.add(
            ErrorLog(
                tenant_id=tenant.id,
                error_type="api_error",
                severity="error",
                message=f"tenant error aged {age}d",
                created_at=_ago(age),
            )
        )
    for age in system_ages:
        db_session.add(
            ErrorLog(
                tenant_id=None,
                error_type="api_error",
                severity="critical",
                message=f"system error aged {age}d",
                created_at=_ago(age),
            )
        )
    for age in access_ages:
        db_session.add(
            ApiAccessLog(
                tenant_id=tenant.id,
                endpoint="/api/matters",
                method="GET",
                status_code=200,
                latency_ms=11.5,
                created_at=_ago(age),
            )
        )
    await db_session.commit()


async def _messages(db_session) -> set[str]:
    return set((await db_session.scalars(select(ErrorLog.message))).all())


async def _count(db_session, model) -> int:
    return int(await db_session.scalar(select(func.count(model.id))) or 0)


@pytest.mark.asyncio
async def test_sweep_removes_expired_rows_and_keeps_recent_ones(
    db_session, test_tenant, retention_settings, bind_sweep
):
    await _seed(
        db_session,
        test_tenant,
        error_ages=(120, 91, 89, 1),
        access_ages=(45, 31, 29, 0.5),
        system_ages=(200, 2),
    )

    result = await log_retention.purge_expired_logs()

    assert result.error_logs_deleted == 3  # two tenant rows + one system row
    assert result.access_logs_deleted == 2
    assert result.incomplete is False

    surviving = await _messages(db_session)
    assert surviving == {
        "tenant error aged 89d",
        "tenant error aged 1d",
        "system error aged 2d",
    }
    assert await _count(db_session, ApiAccessLog) == 2


@pytest.mark.asyncio
async def test_sweep_is_idempotent(
    db_session, test_tenant, retention_settings, bind_sweep
):
    await _seed(db_session, test_tenant, error_ages=(120, 1), access_ages=(45, 1))

    first = await log_retention.purge_expired_logs()
    second = await log_retention.purge_expired_logs()

    assert (first.error_logs_deleted, first.access_logs_deleted) == (1, 1)
    assert second.total_deleted == 0
    assert await _count(db_session, ErrorLog) == 1
    assert await _count(db_session, ApiAccessLog) == 1


@pytest.mark.asyncio
async def test_disabled_retention_deletes_nothing(
    db_session, test_tenant, retention_settings, bind_sweep, monkeypatch
):
    monkeypatch.setattr(retention_settings, "LOG_RETENTION_ENABLED", False)
    await _seed(db_session, test_tenant, error_ages=(400,), access_ages=(400,))

    result = await log_retention.purge_expired_logs()

    assert result.total_deleted == 0
    assert await _count(db_session, ErrorLog) == 1
    assert await _count(db_session, ApiAccessLog) == 1


@pytest.mark.asyncio
async def test_zero_window_retains_only_that_table(
    db_session, test_tenant, retention_settings, bind_sweep, monkeypatch
):
    """A litigation hold on errors must not also stop access-log pruning."""

    monkeypatch.setattr(retention_settings, "ERROR_LOG_RETENTION_DAYS", 0)
    await _seed(db_session, test_tenant, error_ages=(400,), access_ages=(400,))

    result = await log_retention.purge_expired_logs()

    assert result.error_logs_deleted == 0
    assert result.access_logs_deleted == 1
    assert await _count(db_session, ErrorLog) == 1
    assert await _count(db_session, ApiAccessLog) == 0


@pytest.mark.asyncio
async def test_backlog_drains_across_multiple_batches(
    db_session, test_tenant, retention_settings, bind_sweep, monkeypatch
):
    monkeypatch.setattr(retention_settings, "LOG_RETENTION_BATCH_SIZE", 2)
    await _seed(
        db_session, test_tenant, error_ages=(), access_ages=[40 + n for n in range(7)]
    )

    result = await log_retention.purge_expired_logs()

    assert result.access_logs_deleted == 7
    assert result.incomplete is False
    assert await _count(db_session, ApiAccessLog) == 0


@pytest.mark.asyncio
async def test_batch_cap_reports_incomplete_and_leaves_the_rest(
    db_session, test_tenant, retention_settings, bind_sweep, monkeypatch
):
    """Hitting the per-scope budget must be visible, not silently partial."""

    monkeypatch.setattr(retention_settings, "LOG_RETENTION_BATCH_SIZE", 2)
    monkeypatch.setattr(retention_settings, "LOG_RETENTION_MAX_BATCHES_PER_SCOPE", 1)
    await _seed(
        db_session, test_tenant, error_ages=(), access_ages=[40 + n for n in range(5)]
    )

    result = await log_retention.purge_expired_logs()

    assert result.access_logs_deleted == 2
    assert result.incomplete is True
    assert await _count(db_session, ApiAccessLog) == 3


@pytest.mark.asyncio
async def test_each_tenant_is_swept_in_its_own_scope(
    db_session, test_tenant, retention_settings, bind_sweep
):
    other = Tenant(
        id=uuid.uuid4(),
        name="Second Firm",
        domain="secondfirm.com",
        billing_tier="payg",
        is_active=True,
    )
    db_session.add(other)
    await db_session.commit()

    await _seed(db_session, test_tenant, error_ages=(120,), access_ages=())
    await _seed(db_session, other, error_ages=(120, 2), access_ages=())

    result = await log_retention.purge_expired_logs()

    assert result.error_logs_deleted == 2
    assert await _messages(db_session) == {"tenant error aged 2d"}
