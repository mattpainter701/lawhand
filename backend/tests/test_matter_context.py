import pytest

from app.services.cache import ExpertiseCacheManager
from app.services.matter_context import MatterContextService


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.deleted = []

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, _ttl, value):
        self.values[key] = value

    async def delete(self, *keys):
        self.deleted.extend(keys)
        for key in keys:
            self.values.pop(key, None)


class FakeSettingResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSettingDb:
    def __init__(self, value):
        self.value = value

    async def execute(self, _query):
        return FakeSettingResult(self.value)


def test_format_injects_high_value_matter_fields():
    context = MatterContextService().format_matter_context(
        {
            "matter_name": "Acme acquisition",
            "description": "Acme is acquiring Northstar.",
            "memory_content": "CEO needs same-day approval advice.",
            "initial_posture": "Seek a narrow indemnity cap.",
            "key_dates": {"Signing": "2026-09-01", "Closing": "2026-10-15"},
            "risk_level": "high",
            "materiality": "material",
            "exposure_range": "$2m-$5m",
            "retainers": [
                {"type": "evergreen", "amount": 15000, "current_balance": 12000}
            ],
            "recent_communications": [
                {
                    "direction": "outbound",
                    "channel": "email",
                    "subject": "Indemnity proposal",
                    "summary": "Counterparty requested a cap revision.",
                }
            ],
        }
    )

    assert "Description: Acme is acquiring Northstar." in context
    assert "Matter Memory: CEO needs same-day approval advice." in context
    assert "Initial Posture: Seek a narrow indemnity cap." in context
    assert "Key Dates:" in context
    assert "Exposure Range: $2m-$5m" in context
    assert "Active Retainers:" in context
    assert "Recent Communications:" in context


def test_every_open_task_is_rendered_not_just_the_first_few():
    """A truncated task list reads as complete, so the formatter lists all of them."""
    service = MatterContextService()
    tasks = [
        {
            "title": f"Task {index}",
            "status": "pending",
            "task_type": "general",
            "priority": "medium",
            "due_date": "2026-09-20",
        }
        for index in range(8)
    ]

    rendered = service.format_matter_context(
        {"matter_name": "Acme acquisition", "open_tasks": tasks}
    )

    assert "Open Tasks (8):" in rendered
    # MAX_RECENT_ITEMS caps notes and events at 5; tasks must not inherit it.
    for index in range(8):
        assert f"Task {index}" in rendered
    assert "more open tasks exist" not in rendered


def test_a_truncated_task_list_says_so():
    service = MatterContextService()

    rendered = service.format_matter_context(
        {
            "matter_name": "Acme acquisition",
            "open_tasks": [{"title": "Task", "status": "pending", "priority": "high"}],
            "open_tasks_truncated": True,
        }
    )

    assert "more open tasks exist" in rendered


def test_no_open_tasks_is_stated_rather_than_left_blank():
    rendered = MatterContextService().format_matter_context(
        {"matter_name": "Acme acquisition", "open_tasks": []}
    )

    assert "Open Tasks: none" in rendered


def test_privacy_mode_redacts_task_titles_but_keeps_workflow_metadata():
    service = MatterContextService()

    scrubbed = service.scrub_matter_context(
        {
            "open_tasks": [
                {
                    "title": "Call Jane Doe about the settlement",
                    "status": "waiting",
                    "priority": "high",
                    "due_date": "2026-09-20",
                }
            ]
        },
        privacy_mode=True,
    )
    rendered = service.format_matter_context(scrubbed, scrubbed=True)

    assert "Jane" not in rendered
    assert "[waiting]" in rendered
    assert "2026-09-20" in rendered


def test_privacy_mode_redacts_new_free_text_context_fields():
    service = MatterContextService()
    scrubbed = service.scrub_matter_context(
        {
            "description": "Client Jane Doe is acquiring Northstar.",
            "memory_content": "Jane's direct number is 555-0100.",
            "initial_posture": "Call Jane before settlement.",
            "recent_events": [{"content": "Jane approved the proposal."}],
            "recent_communications": [
                {"subject": "Jane's approval", "summary": "Call 555-0100"}
            ],
        },
        privacy_mode=True,
    )
    rendered = service.format_matter_context(scrubbed, scrubbed=True)

    assert "Jane" not in rendered
    assert "555-0100" not in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_value", "expected"),
    [(None, True), (True, True), (False, False)],
)
async def test_matter_context_feature_setting_defaults_on(stored_value, expected):
    service = MatterContextService()

    assert await service.is_enabled(FakeSettingDb(stored_value), "tenant-a") is expected


@pytest.mark.asyncio
async def test_invalidate_matter_context_removes_only_targeted_entry():
    cache = ExpertiseCacheManager()
    cache.cache_enabled = True
    cache.redis_client = FakeRedis()
    target = cache._make_key("matter", "tenant-a", "matter-a", "standard")
    other = cache._make_key("matter", "tenant-a", "matter-b", "standard")
    cache.redis_client.values[target] = "stale"
    cache.redis_client.values[other] = "keep"

    assert await cache.invalidate_matter_context("matter-a", "tenant-a")
    assert target not in cache.redis_client.values
    assert cache.redis_client.values[other] == "keep"


@pytest.mark.asyncio
async def test_next_chat_context_is_fresh_after_invalidation():
    cache = ExpertiseCacheManager()
    cache.cache_enabled = True
    cache.redis_client = FakeRedis()

    await cache.set_cached_matter_context("matter-a", "tenant-a", "old memory")
    assert await cache.get_cached_matter_context("matter-a", "tenant-a") == "old memory"

    await cache.invalidate_matter_context("matter-a", "tenant-a")
    assert await cache.get_cached_matter_context("matter-a", "tenant-a") is None

    await cache.set_cached_matter_context("matter-a", "tenant-a", "updated memory")
    assert (
        await cache.get_cached_matter_context("matter-a", "tenant-a")
        == "updated memory"
    )


@pytest.mark.asyncio
async def test_privacy_context_uses_a_separate_cache_entry():
    cache = ExpertiseCacheManager()
    cache.cache_enabled = True
    cache.redis_client = FakeRedis()

    await cache.set_cached_matter_context(
        "matter-a", "tenant-a", "full", privacy_mode=False
    )
    await cache.set_cached_matter_context(
        "matter-a", "tenant-a", "redacted", privacy_mode=True
    )

    assert await cache.get_cached_matter_context("matter-a", "tenant-a") == "full"
    assert (
        await cache.get_cached_matter_context("matter-a", "tenant-a", privacy_mode=True)
        == "redacted"
    )


@pytest.mark.asyncio
async def test_matter_context_loads_every_open_task_and_omits_closed_ones(
    db_session, test_tenant, test_user
):
    """The assistant answered "what is outstanding?" without any task data.

    Matter context carried notes, events and communications but no tasks, so a
    task list could only come from whatever a note happened to mention.
    """
    import uuid as _uuid

    from app.models.plugin import Matter
    from app.models.task import Task

    matter_id = _uuid.uuid4()
    db_session.add(
        Matter(
            id=matter_id,
            tenant_id=test_tenant.id,
            user_id=test_user.id,
            slug=f"context-tasks-{matter_id.hex[:8]}",
            matter_name="Acme acquisition",
            matter_type="litigation",
        )
    )
    await db_session.flush()
    statuses = ["pending", "in_progress", "waiting", "review", "completed", "cancelled"]
    for status in statuses:
        db_session.add(
            Task(
                id=_uuid.uuid4(),
                tenant_id=test_tenant.id,
                matter_id=matter_id,
                title=f"{status} task",
                task_type="general",
                priority="medium",
                status=status,
            )
        )
    await db_session.commit()

    context, _has_pii, _findings = await MatterContextService().get_matter_context(
        db_session, str(matter_id), tenant_id=test_tenant.id
    )

    titles = {task["title"] for task in context["open_tasks"]}
    assert titles == {
        "pending task",
        "in_progress task",
        "waiting task",
        "review task",
    }
    assert context["open_tasks_truncated"] is False
