"""D07: leaving a matter takes back the cloud folder share LawHand gave.

Assigning someone to a matter shares its OneDrive / Google Drive folders with
them. These tests drive the real routes against an in-memory provider that
behaves like Graph and Drive (permission ids, merged repeat invites, inherited
permissions) and prove that removing or deactivating the person removes
LawHand's share, leaves shares a person made directly, and never lets a
provider failure block the unassign.
"""

import itertools
import json
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.models.durable_job import DurableJob
from app.models.error_log import ErrorLog
from app.models.integration_sync_run import IntegrationSyncRun
from app.models.matter_assignment import MatterAssignment
from app.models.matter_folder_share_grant import MatterFolderShareGrant
from app.models.plugin import Matter, MatterEvent
from app.models.user import User
from app.services import cloud_init, matter_folder_shares

ASSIGNEE = "associate@testfirm.com"
BYSTANDER = "partner@testfirm.com"
LAWHAND_ROLE = {"onedrive": "write", "google_drive": "writer"}
CONTEXT_ROLE = {"onedrive": "read", "google_drive": "reader"}
AUTH_PROVIDER = {"onedrive": "microsoft", "google_drive": "google"}
PROVIDERS = ["onedrive", "google_drive"]


class FakeDrives:
    """A tiny Graph + Drive permissions API keyed by (provider, folder id)."""

    def __init__(self):
        self.permissions: dict[tuple[str, str], dict[str, dict]] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail_deletes: int | None = None
        self.raise_on_delete: Exception | None = None
        self.fail_posts: int | None = None
        self.fail_gets: int | None = None
        self.omit_ids = False
        self._ids = itertools.count(1)

    # ── seeding ──
    def seed(self, provider, folder, email, role, *, inherited=False) -> str:
        perm_id = f"{provider}-perm-{next(self._ids)}"
        self.permissions.setdefault((provider, folder), {})[perm_id] = {
            "email": email,
            "role": role,
            "inherited": inherited,
        }
        return perm_id

    def holders(self, provider, folder) -> dict[str, str]:
        return {
            p["email"]: p["role"]
            for p in self.permissions.get((provider, folder), {}).values()
        }

    def ids_for(self, provider, folder, email) -> list[str]:
        return [
            perm_id
            for perm_id, p in self.permissions.get((provider, folder), {}).items()
            if p["email"] == email
        ]

    # ── provider wire format ──
    @staticmethod
    def _graph(perm_id, p):
        body = {
            "id": perm_id,
            "roles": [p["role"]],
            "grantedToV2": {"user": {"email": p["email"], "displayName": "x"}},
        }
        if p["inherited"]:
            body["inheritedFrom"] = {"id": "parent"}
        return body

    @staticmethod
    def _drive(perm_id, p):
        return {
            "id": perm_id,
            "type": "user",
            "emailAddress": p["email"],
            "role": p["role"],
            "permissionDetails": [{"inherited": p["inherited"]}],
        }

    def _grant(self, provider, folder, email, role) -> str:
        # Like both providers: a repeat invite merges into the direct share.
        for perm_id, p in self.permissions.get((provider, folder), {}).items():
            if p["email"] == email and not p["inherited"]:
                return perm_id
        return self.seed(provider, folder, email, role)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        parts = path.strip("/").split("/")
        if request.url.host == "graph.microsoft.com":
            provider, folder = "onedrive", parts[4]
            tail = parts[5:]
            fmt = self._graph
        else:
            provider, folder = "google_drive", parts[3]
            tail = parts[4:]
            fmt = self._drive
        perms = self.permissions.setdefault((provider, folder), {})
        if request.method == "POST":
            if self.fail_posts:
                return httpx.Response(self.fail_posts, json={"error": "down"})
            body = json.loads(request.content)
            if provider == "onedrive":
                email, role = body["recipients"][0]["email"], body["roles"][0]
            else:
                email, role = body["emailAddress"], body["role"]
            perm_id = self._grant(provider, folder, email, role)
            wire = fmt(perm_id, perms[perm_id])
            if self.omit_ids:
                wire.pop("id")
            return httpx.Response(
                200, json={"value": [wire]} if provider == "onedrive" else wire
            )
        if request.method == "GET":
            if self.fail_gets:
                return httpx.Response(self.fail_gets, json={"error": "down"})
            items = [fmt(perm_id, p) for perm_id, p in perms.items()]
            key = "value" if provider == "onedrive" else "permissions"
            return httpx.Response(200, json={key: items})
        if request.method == "DELETE":
            if self.raise_on_delete is not None:
                raise self.raise_on_delete
            if self.fail_deletes:
                return httpx.Response(self.fail_deletes, json={"error": "denied"})
            perm_id = tail[-1]
            if perms.pop(perm_id, None) is None:
                return httpx.Response(404)
            return httpx.Response(204)
        return httpx.Response(500)


@pytest.fixture
def drives(monkeypatch):
    fake = FakeDrives()
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        cloud_init.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(fake.handler), **kwargs
        ),
    )
    fake.token = "provider-token"

    async def fresh_token(_db, _tenant_id, _provider):
        return fake.token

    async def prefer_service_account(_db, _tenant_id, token, **_kwargs):
        return token

    monkeypatch.setattr(cloud_init, "get_fresh_token", fresh_token)
    monkeypatch.setattr(
        cloud_init.google_service_account,
        "prefer_service_account",
        prefer_service_account,
    )
    return fake


async def _user(db_session, tenant, email, *, active=True):
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=email,
        full_name=email.split("@")[0].title(),
        role="user",
        is_active=active,
    )
    db_session.add(user)
    await db_session.commit()
    return user


def _folder(provider, folder_id="matter-folder", context=None):
    cloud_folder = {provider: {"matter_folder_id": folder_id}}
    if context:
        cloud_folder["context_folders"] = [
            {"id": str(uuid.uuid4()), "provider": provider, "matter_folder_id": context}
        ]
    return cloud_folder


async def _matter(db_session, tenant, owner, cloud_folder, name="Acme v Beta"):
    matter = Matter(
        tenant_id=tenant.id,
        user_id=owner.id,
        slug=f"m-{uuid.uuid4().hex[:8]}",
        matter_name=name,
        cloud_folder=cloud_folder,
    )
    db_session.add(matter)
    await db_session.commit()
    return matter


async def _assign(client, matter_id, user_id):
    resp = await client.post(
        f"/api/matters/{matter_id}/assignments",
        json={"user_id": str(user_id), "role": "associate"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _grants(db_session, **filters):
    stmt = select(MatterFolderShareGrant)
    for key, value in filters.items():
        stmt = stmt.where(getattr(MatterFolderShareGrant, key) == value)
    db_session.expire_all()
    return list((await db_session.scalars(stmt)).all())


# ── unassign ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_unassign_removes_lawhand_share_and_reassign_grants_again(
    client, db_session, test_tenant, test_user, drives, provider
):
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    matter = await _matter(
        db_session, test_tenant, test_user, _folder(provider, context="ctx-folder")
    )
    matter_id, assignee_id, tenant_id = matter.id, assignee.id, test_tenant.id

    assignment_id = await _assign(client, matter_id, assignee_id)
    assert drives.holders(provider, "matter-folder") == {
        ASSIGNEE: LAWHAND_ROLE[provider]
    }
    assert drives.holders(provider, "ctx-folder") == {ASSIGNEE: CONTEXT_ROLE[provider]}
    granted = await _grants(db_session, matter_id=matter_id)
    assert {(g.folder_id, g.origin, g.status) for g in granted} == {
        ("matter-folder", "lawhand", "active"),
        ("ctx-folder", "lawhand", "active"),
    }
    assert all(g.permission_id and g.user_id == assignee_id for g in granted)

    resp = await client.delete(f"/api/matters/{matter_id}/assignments/{assignment_id}")

    assert resp.status_code == 204
    assert drives.holders(provider, "matter-folder") == {}
    assert drives.holders(provider, "ctx-folder") == {}
    revoked = await _grants(db_session, matter_id=matter_id)
    assert {g.status for g in revoked} == {"revoked"}
    events = (
        await db_session.scalars(
            select(MatterEvent).where(MatterEvent.matter_id == matter_id)
        )
    ).all()
    assert [e.event_type for e in events] == ["cloud_folder_unshared"]
    assert ASSIGNEE in events[0].title
    run = await db_session.scalar(
        select(IntegrationSyncRun).where(
            IntegrationSyncRun.tenant_id == tenant_id,
            IntegrationSyncRun.job_type == "matter_folder_unshare",
        )
    )
    assert (run.provider, run.status, run.items_ok) == (
        AUTH_PROVIDER[provider],
        "success",
        2,
    )

    # Re-assigning shares the folders again with a fresh LawHand permission.
    await _assign(client, matter_id, assignee_id)
    assert drives.holders(provider, "matter-folder") == {
        ASSIGNEE: LAWHAND_ROLE[provider]
    }
    again = await _grants(db_session, matter_id=matter_id)
    assert {g.status for g in again} == {"active"}
    assert all(
        g.permission_id in drives.ids_for(provider, g.folder_id, ASSIGNEE)
        for g in again
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_unassign_leaves_shares_a_person_added_directly(
    client, db_session, test_tenant, test_user, drives, provider
):
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    matter = await _matter(db_session, test_tenant, test_user, _folder(provider))
    matter_id = matter.id
    # Added in OneDrive / Drive by a person, not by LawHand.
    other_share = drives.seed(provider, "matter-folder", BYSTANDER, "write")
    # The assignee already had a lesser direct share before LawHand invited them;
    # the provider merges LawHand's invite into it.
    own_share = drives.seed(provider, "matter-folder", ASSIGNEE, "commenter")
    inherited = drives.seed(
        provider, "matter-folder", ASSIGNEE, LAWHAND_ROLE[provider], inherited=True
    )

    assignment_id = await _assign(client, matter_id, assignee.id)
    (grant,) = await _grants(db_session, matter_id=matter_id)
    assert (grant.origin, grant.permission_id) == ("preexisting", own_share)

    resp = await client.delete(f"/api/matters/{matter_id}/assignments/{assignment_id}")

    assert resp.status_code == 204
    remaining = drives.permissions[(provider, "matter-folder")]
    assert {other_share, own_share, inherited} <= set(remaining)
    assert not any(method == "DELETE" for method, _ in drives.calls)
    (grant,) = await _grants(db_session, matter_id=matter_id)
    assert grant.status == "kept"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_share_made_before_ids_were_stored_is_matched_on_email_and_role(
    client, db_session, test_tenant, test_user, drives, provider
):
    """Legacy grants: the person's email plus LawHand's exact role on the folder."""
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    matter = await _matter(
        db_session, test_tenant, test_user, _folder(provider, context="ctx-folder")
    )
    matter_id = matter.id
    legacy_write = drives.seed(
        provider, "matter-folder", ASSIGNEE, LAWHAND_ROLE[provider]
    )
    legacy_read = drives.seed(provider, "ctx-folder", ASSIGNEE, CONTEXT_ROLE[provider])
    bystander = drives.seed(
        provider, "matter-folder", BYSTANDER, LAWHAND_ROLE[provider]
    )
    inherited = drives.seed(
        provider, "matter-folder", ASSIGNEE, LAWHAND_ROLE[provider], inherited=True
    )
    owner = drives.seed(provider, "ctx-folder", ASSIGNEE, "owner")
    assignment = MatterAssignment(
        tenant_id=test_tenant.id, matter_id=matter_id, user_id=assignee.id
    )
    db_session.add(assignment)
    await db_session.commit()

    resp = await client.delete(f"/api/matters/{matter_id}/assignments/{assignment.id}")

    assert resp.status_code == 204
    assert legacy_write not in drives.permissions[(provider, "matter-folder")]
    assert legacy_read not in drives.permissions[(provider, "ctx-folder")]
    assert bystander in drives.permissions[(provider, "matter-folder")]
    assert inherited in drives.permissions[(provider, "matter-folder")]
    assert owner in drives.permissions[(provider, "ctx-folder")]
    grants = await _grants(db_session, matter_id=matter_id)
    assert {(g.origin, g.status) for g in grants} == {("legacy", "revoked")}


# ── fail safe ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "failure"),
    [
        ("onedrive", "forbidden"),
        ("google_drive", "forbidden"),
        ("onedrive", "network"),
        ("google_drive", "token_expired"),
    ],
)
async def test_provider_failure_never_blocks_unassign_and_is_retried(
    client, db_session, test_tenant, test_user, drives, provider, failure
):
    from app.services.durable_job_worker import process_job

    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    matter = await _matter(db_session, test_tenant, test_user, _folder(provider))
    matter_id, tenant_id = matter.id, test_tenant.id
    assignment_id = await _assign(client, matter_id, assignee.id)
    if failure == "forbidden":
        drives.fail_deletes = 403
    elif failure == "network":
        drives.raise_on_delete = httpx.ConnectError("provider unreachable")
    else:
        drives.token = None

    resp = await client.delete(f"/api/matters/{matter_id}/assignments/{assignment_id}")

    assert resp.status_code == 204
    assert await db_session.get(MatterAssignment, uuid.UUID(assignment_id)) is None
    assert drives.holders(provider, "matter-folder") == {
        ASSIGNEE: LAWHAND_ROLE[provider]
    }
    (grant,) = await _grants(db_session, matter_id=matter_id)
    assert (grant.status, grant.revoke_attempts) == ("revoke_pending", 1)
    assert grant.last_error
    event = await db_session.scalar(
        select(MatterEvent).where(MatterEvent.matter_id == matter_id)
    )
    assert event.event_type == "cloud_folder_unshare_failed"
    run = await db_session.scalar(
        select(IntegrationSyncRun).where(
            IntegrationSyncRun.job_type == "matter_folder_unshare"
        )
    )
    assert (run.provider, run.status, run.items_failed) == (
        AUTH_PROVIDER[provider],
        "failed",
        1,
    )
    error = await db_session.scalar(
        select(ErrorLog).where(ErrorLog.error_type == "integration_sync_error")
    )
    assert "matter_folder_unshare" in error.message
    job = await db_session.scalar(
        select(DurableJob).where(DurableJob.kind == "matter_folder_unshare")
    )
    assert job.status == "pending"
    assert job.max_attempts == matter_folder_shares.UNSHARE_JOB_MAX_ATTEMPTS
    job_id = job.id

    # A worker attempt while the provider is still failing backs off.
    assert await process_job(job_id, tenant_id) is True
    db_session.expire_all()
    job = await db_session.get(DurableJob, job_id)
    assert job.status == "pending" and job.attempts == 1
    assert "could not be removed" in job.last_error

    # Once the provider recovers the queued retry removes the share.
    drives.fail_deletes = None
    drives.raise_on_delete = None
    drives.token = "provider-token"
    job.available_at = job.created_at
    await db_session.commit()
    assert await process_job(job_id, tenant_id) is True
    db_session.expire_all()
    assert (await db_session.get(DurableJob, job_id)).status == "completed"
    assert drives.holders(provider, "matter-folder") == {}
    (grant,) = await _grants(db_session, matter_id=matter_id)
    assert grant.status == "revoked"
    types = (
        await db_session.scalars(
            select(MatterEvent.event_type)
            .where(MatterEvent.matter_id == matter_id)
            .order_by(MatterEvent.created_at)
        )
    ).all()
    assert list(types) == ["cloud_folder_unshare_failed", "cloud_folder_unshared"]


@pytest.mark.asyncio
async def test_reassigning_before_the_retry_cancels_the_pending_removal(
    client, db_session, test_tenant, test_user, drives
):
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    matter = await _matter(db_session, test_tenant, test_user, _folder("onedrive"))
    matter_id = matter.id
    assignment_id = await _assign(client, matter_id, assignee.id)
    drives.fail_deletes = 503
    await client.delete(f"/api/matters/{matter_id}/assignments/{assignment_id}")
    drives.fail_deletes = None
    # Re-assigned while the provider is unreachable, so the share is not re-made.
    drives.token = None
    await _assign(client, matter_id, assignee.id)
    drives.token = "provider-token"

    summary = await matter_folder_shares.process_pending_revocations(
        db_session, test_tenant.id
    )

    assert summary["restored"] == 1 and summary["revoked"] == 0
    assert drives.holders("onedrive", "matter-folder") == {ASSIGNEE: "write"}
    (grant,) = await _grants(db_session, matter_id=matter_id)
    assert grant.status == "active"


@pytest.mark.asyncio
async def test_folder_linked_to_two_matters_stays_shared_until_both_end(
    client, db_session, test_tenant, test_user, drives
):
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    first = await _matter(
        db_session, test_tenant, test_user, _folder("google_drive", "f1", "shared")
    )
    second = await _matter(
        db_session, test_tenant, test_user, _folder("google_drive", "f2", "shared")
    )
    first_id, second_id = first.id, second.id
    a1 = await _assign(client, first_id, assignee.id)
    a2 = await _assign(client, second_id, assignee.id)

    await client.delete(f"/api/matters/{first_id}/assignments/{a1}")
    assert drives.holders("google_drive", "shared") == {ASSIGNEE: "reader"}
    assert drives.holders("google_drive", "f1") == {}

    await client.delete(f"/api/matters/{second_id}/assignments/{a2}")
    assert drives.holders("google_drive", "shared") == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_legacy_context_folder_stays_shared_while_another_matter_needs_it(
    client, db_session, test_tenant, test_user, drives, provider
):
    """Two matters from before ids were stored link one context folder.

    Neither has grant rows, so leaving the first must still keep the read
    share the second matter relies on, and leaving both removes it.
    """
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    first = await _matter(
        db_session, test_tenant, test_user, _folder(provider, "f1", "shared")
    )
    second = await _matter(
        db_session, test_tenant, test_user, _folder(provider, "f2", "shared")
    )
    first_id, second_id = first.id, second.id
    drives.seed(provider, "f1", ASSIGNEE, LAWHAND_ROLE[provider])
    drives.seed(provider, "f2", ASSIGNEE, LAWHAND_ROLE[provider])
    drives.seed(provider, "shared", ASSIGNEE, CONTEXT_ROLE[provider])
    a1 = MatterAssignment(
        tenant_id=test_tenant.id, matter_id=first_id, user_id=assignee.id
    )
    a2 = MatterAssignment(
        tenant_id=test_tenant.id, matter_id=second_id, user_id=assignee.id
    )
    db_session.add_all([a1, a2])
    await db_session.commit()
    a1_id, a2_id = a1.id, a2.id

    resp = await client.delete(f"/api/matters/{first_id}/assignments/{a1_id}")

    assert resp.status_code == 204
    assert drives.holders(provider, "f1") == {}
    assert drives.holders(provider, "shared") == {ASSIGNEE: CONTEXT_ROLE[provider]}

    resp = await client.delete(f"/api/matters/{second_id}/assignments/{a2_id}")

    assert resp.status_code == 204
    assert drives.holders(provider, "f2") == {}
    assert drives.holders(provider, "shared") == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_share_failure_never_blocks_the_assignment(
    client, db_session, test_tenant, test_user, drives, provider
):
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    matter = await _matter(db_session, test_tenant, test_user, _folder(provider))
    matter_id = matter.id
    drives.fail_posts = 500

    await _assign(client, matter_id, assignee.id)

    assert drives.holders(provider, "matter-folder") == {}
    assert await _grants(db_session, matter_id=matter_id) == []


@pytest.mark.asyncio
async def test_immediate_unshare_errors_never_escape_the_request(
    db_session, test_tenant, monkeypatch
):
    async def broken(*_args, **_kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(matter_folder_shares, "process_pending_revocations", broken)

    assert (
        await matter_folder_shares.revoke_pending_shares_now(
            db_session, test_tenant.id, email=ASSIGNEE
        )
        is None
    )


# ── recording which share is LawHand's ──────────────────────────────────


@pytest.mark.asyncio
async def test_repeat_share_keeps_what_each_permission_was_recorded_as(
    client, db_session, test_tenant, test_user, drives
):
    """Provisioning re-shares with every assignee; the records must not drift."""
    from app.routers.matters import _share_matter_with_assignees

    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    bystander = await _user(db_session, test_tenant, BYSTANDER)
    matter = await _matter(db_session, test_tenant, test_user, _folder("onedrive"))
    matter_id, tenant_id = matter.id, test_tenant.id
    human_share = drives.seed("onedrive", "matter-folder", BYSTANDER, "read")
    await _assign(client, matter_id, assignee.id)
    await _assign(client, matter_id, bystander.id)
    before = {
        g.grantee_email: (g.origin, g.permission_id)
        for g in await _grants(db_session, matter_id=matter_id)
    }
    assert before[BYSTANDER] == ("preexisting", human_share)
    assert before[ASSIGNEE][0] == "lawhand"

    matter = await db_session.get(Matter, matter_id, populate_existing=True)
    await _share_matter_with_assignees(db_session, tenant_id, matter)

    after = {
        g.grantee_email: (g.origin, g.permission_id)
        for g in await _grants(db_session, matter_id=matter_id)
    }
    assert after == before


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_share_without_a_returned_id_falls_back_to_email_and_role(
    client, db_session, test_tenant, test_user, drives, provider
):
    """Some responses carry no permission id; removal then matches like legacy."""
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    bystander = await _user(db_session, test_tenant, BYSTANDER)
    matter = await _matter(db_session, test_tenant, test_user, _folder(provider))
    matter_id = matter.id
    human_share = drives.seed(provider, "matter-folder", BYSTANDER, "commenter")
    drives.omit_ids = True
    ours = await _assign(client, matter_id, assignee.id)
    theirs = await _assign(client, matter_id, bystander.id)
    origins = {
        g.grantee_email: (g.origin, g.permission_id)
        for g in await _grants(db_session, matter_id=matter_id)
    }
    assert origins == {
        ASSIGNEE: ("legacy", None),
        BYSTANDER: ("preexisting", human_share),
    }

    await client.delete(f"/api/matters/{matter_id}/assignments/{ours}")
    await client.delete(f"/api/matters/{matter_id}/assignments/{theirs}")

    assert drives.holders(provider, "matter-folder") == {BYSTANDER: "commenter"}


@pytest.mark.asyncio
async def test_unreadable_permission_list_still_records_the_new_share(
    client, db_session, test_tenant, test_user, drives
):
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    matter = await _matter(db_session, test_tenant, test_user, _folder("onedrive"))
    matter_id = matter.id
    drives.fail_gets = 500

    assignment_id = await _assign(client, matter_id, assignee.id)
    (grant,) = await _grants(db_session, matter_id=matter_id)
    assert grant.origin == "lawhand" and grant.permission_id

    drives.fail_gets = None
    await client.delete(f"/api/matters/{matter_id}/assignments/{assignment_id}")
    assert drives.holders("onedrive", "matter-folder") == {}


# ── other paths that end or keep access ─────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_deactivating_a_user_removes_every_share_and_reactivating_restores(
    client, db_session, test_tenant, test_user, drives, provider
):
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    first = await _matter(db_session, test_tenant, test_user, _folder(provider, "f1"))
    second = await _matter(db_session, test_tenant, test_user, _folder(provider, "f2"))
    assignee_id = assignee.id
    await _assign(client, first.id, assignee_id)
    await _assign(client, second.id, assignee_id)
    assert drives.holders(provider, "f1") and drives.holders(provider, "f2")

    resp = await client.delete(f"/api/admin/users/{assignee_id}")

    assert resp.status_code == 204
    assert drives.holders(provider, "f1") == {}
    assert drives.holders(provider, "f2") == {}
    assert {g.status for g in await _grants(db_session, user_id=assignee_id)} == {
        "revoked"
    }

    resp = await client.post(f"/api/admin/users/{assignee_id}/reactivate")

    assert resp.status_code == 200
    assert drives.holders(provider, "f1") == {ASSIGNEE: LAWHAND_ROLE[provider]}
    assert drives.holders(provider, "f2") == {ASSIGNEE: LAWHAND_ROLE[provider]}


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_working_on_toggle_is_not_an_access_change(
    client, db_session, test_tenant, test_user, drives, provider
):
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    matter = await _matter(db_session, test_tenant, test_user, _folder(provider))
    assignment_id = await _assign(client, matter.id, assignee.id)

    for active in ("true", "false"):
        resp = await client.patch(
            f"/api/matters/{matter.id}/assignments/{assignment_id}/active",
            params={"active": active},
        )
        assert resp.status_code == 200

    assert drives.holders(provider, "matter-folder") == {
        ASSIGNEE: LAWHAND_ROLE[provider]
    }
    (grant,) = await _grants(db_session, matter_id=matter.id)
    assert grant.status == "active"


@pytest.mark.asyncio
async def test_sharepoint_folder_has_no_per_person_share_to_remove(
    client, db_session, test_tenant, test_user, drives
):
    """SharePoint access follows site membership; LawHand shares nothing there."""
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    matter = await _matter(
        db_session,
        test_tenant,
        test_user,
        {"sharepoint": {"matter_folder_id": "sp-folder", "drive_id": "sp-drive"}},
    )
    matter_id = matter.id
    assignment_id = await _assign(client, matter_id, assignee.id)

    resp = await client.delete(f"/api/matters/{matter_id}/assignments/{assignment_id}")

    assert resp.status_code == 204
    assert drives.calls == []
    assert await _grants(db_session, matter_id=matter_id) == []
    assert (
        await db_session.scalar(
            select(DurableJob).where(DurableJob.kind == "matter_folder_unshare")
        )
        is None
    )


@pytest.mark.asyncio
async def test_matter_reshare_skips_deactivated_assignees(
    db_session, test_tenant, test_user, drives
):
    from app.routers.matters import _share_matter_with_assignees

    active = await _user(db_session, test_tenant, ASSIGNEE)
    inactive = await _user(db_session, test_tenant, BYSTANDER, active=False)
    matter = await _matter(db_session, test_tenant, test_user, _folder("onedrive"))
    for person in (active, inactive):
        db_session.add(
            MatterAssignment(
                tenant_id=test_tenant.id, matter_id=matter.id, user_id=person.id
            )
        )
    await db_session.commit()

    active_id, matter_id = active.id, matter.id

    await _share_matter_with_assignees(db_session, test_tenant.id, matter)

    assert drives.holders("onedrive", "matter-folder") == {ASSIGNEE: "write"}
    (grant,) = await _grants(db_session, matter_id=matter_id)
    assert grant.user_id == active_id and grant.origin == "lawhand"


@pytest.mark.asyncio
async def test_hourly_sweep_requeues_shares_still_pending(
    client, db_session, test_tenant, test_user, drives
):
    assignee = await _user(db_session, test_tenant, ASSIGNEE)
    matter = await _matter(db_session, test_tenant, test_user, _folder("onedrive"))
    assignment_id = await _assign(client, matter.id, assignee.id)
    drives.fail_deletes = 403
    await client.delete(f"/api/matters/{matter.id}/assignments/{assignment_id}")

    assert await matter_folder_shares.enqueue_stale_unshare_jobs() == 1

    db_session.expire_all()
    sweep = await db_session.scalar(
        select(DurableJob).where(
            DurableJob.kind == "matter_folder_unshare",
            DurableJob.idempotency_key == "sweep",
        )
    )
    assert sweep.status == "pending"
    assert sweep.payload == {"matter_id": None, "email": None}


# ── provider wire parsing ───────────────────────────────────────────────


def test_permission_normalization_marks_inherited_and_non_user_shares():
    graph = cloud_init.normalize_folder_permission(
        "onedrive",
        {
            "id": "p1",
            "roles": ["write"],
            "grantedToIdentitiesV2": [{"siteUser": {"email": "A@Firm.com"}}],
            "invitation": {"email": "b@firm.com"},
            "inheritedFrom": {"id": "parent"},
        },
    )
    assert graph == {
        "id": "p1",
        "emails": {"a@firm.com", "b@firm.com"},
        "roles": {"write"},
        "direct": False,
    }
    drive_group = cloud_init.normalize_folder_permission(
        "google_drive",
        {
            "id": "p2",
            "type": "group",
            "emailAddress": "team@firm.com",
            "role": "writer",
        },
    )
    assert drive_group["direct"] is False
    shared_drive = cloud_init.normalize_folder_permission(
        "google_drive",
        {
            "id": "p3",
            "type": "user",
            "emailAddress": "c@firm.com",
            "role": "writer",
            "permissionDetails": [{"inherited": True}, {"inherited": False}],
        },
    )
    assert shared_drive["direct"] is True
    assert cloud_init.normalize_folder_permission("onedrive", {"roles": []}) is None


def test_permission_id_is_read_from_both_response_shapes():
    assert (
        cloud_init._first_permission_id(
            httpx.Response(200, json={"value": [{"id": "g1"}]})
        )
        == "g1"
    )
    assert cloud_init._first_permission_id(httpx.Response(200, json={"id": "d1"})) == (
        "d1"
    )
    assert cloud_init._first_permission_id(httpx.Response(202, text="")) is None
    assert cloud_init._first_permission_id(httpx.Response(200, json=[1])) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_permission_listing_follows_provider_paging(monkeypatch, provider):
    pages = []

    def handler(request):
        pages.append(request.url)
        second = request.url.params.get("pageToken") == "next" or "skiptoken" in str(
            request.url
        )
        if provider == "onedrive":
            body = {"value": [{"id": "two" if second else "one", "roles": ["read"]}]}
            if not second:
                body["@odata.nextLink"] = (
                    "https://graph.microsoft.com/v1.0/next?$skiptoken=next"
                )
        else:
            body = {
                "permissions": [{"id": "two" if second else "one", "role": "reader"}]
            }
            if not second:
                body["nextPageToken"] = "next"
        return httpx.Response(200, json=body)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        cloud_init.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    listed = await cloud_init.list_folder_permissions("t", provider, "folder")

    assert [p["id"] for p in listed] == ["one", "two"]
    assert len(pages) == 2


@pytest.mark.asyncio
async def test_permission_listing_and_delete_surface_provider_errors(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        cloud_init.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(401)),
            **kwargs,
        ),
    )

    with pytest.raises(RuntimeError, match="401"):
        await cloud_init.list_folder_permissions("t", "google_drive", "folder")
    with pytest.raises(RuntimeError, match="401"):
        await cloud_init.delete_folder_permission("t", "onedrive", "folder", "p")
