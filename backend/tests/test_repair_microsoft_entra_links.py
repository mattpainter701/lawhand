import uuid
import json
from unittest.mock import AsyncMock

import pytest
from jose import jwt

from app.models.tenant import Tenant
from app.models.user import User
from scripts import repair_microsoft_entra_links as repair_script
from scripts.repair_microsoft_entra_links import plan_links

ENTRA_TENANT = "11111111-1111-4111-8111-111111111111"
OWNER_OID = "22222222-2222-4222-8222-222222222222"
STAFF_OID = "33333333-3333-4333-8333-333333333333"


def _user(email: str, **overrides) -> User:
    values = {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "email": email,
        "oauth_provider": "microsoft",
        "oauth_subject": "old-pairwise-subject",
        "principal_type": "human",
        "is_active": True,
    }
    values.update(overrides)
    return User(**values)


def _graph(object_id: str, email: str, **overrides) -> dict:
    values = {
        "id": object_id,
        "mail": email,
        "userPrincipalName": email,
        "accountEnabled": True,
        "userType": "Member",
    }
    values.update(overrides)
    return values


def test_plans_all_existing_tenant_domain_users_and_keeps_old_subject():
    owner = _user("services@bismarcklaw.com")
    staff = _user("staff@bismarcklaw.com", oauth_subject=STAFF_OID)
    plan = plan_links(
        [owner, staff],
        [_graph(OWNER_OID, owner.email), _graph(STAFF_OID, staff.email)],
        ENTRA_TENANT,
        "bismarcklaw.com",
    )

    assert {item["email"] for item in plan["links"]} == {
        owner.email,
        staff.email,
    }
    assert owner.oauth_subject == "old-pairwise-subject"
    assert owner.entra_object_id is None
    assert plan["skipped"] == []


def test_skips_guests_disabled_users_other_domains_and_other_providers():
    users = [
        _user("guest@bismarcklaw.com"),
        _user("disabled@bismarcklaw.com"),
        _user("external@gmail.com"),
        _user("google@bismarcklaw.com", oauth_provider="google"),
        _user("inactive@bismarcklaw.com", is_active=False),
    ]
    graph = [
        _graph(OWNER_OID, "guest@bismarcklaw.com", userType="Guest"),
        _graph(STAFF_OID, "disabled@bismarcklaw.com", accountEnabled=False),
        _graph(str(uuid.uuid4()), "external@gmail.com"),
        _graph(str(uuid.uuid4()), "google@bismarcklaw.com"),
        _graph(str(uuid.uuid4()), "inactive@bismarcklaw.com"),
    ]
    plan = plan_links(users, graph, ENTRA_TENANT, "bismarcklaw.com")
    assert plan["links"] == []
    assert len(plan["skipped"]) == 5


def test_rejects_ambiguous_graph_addresses():
    with pytest.raises(ValueError, match="Ambiguous Graph identity"):
        plan_links(
            [_user("services@bismarcklaw.com")],
            [
                _graph(OWNER_OID, "services@bismarcklaw.com"),
                _graph(STAFF_OID, "services@bismarcklaw.com"),
            ],
            ENTRA_TENANT,
            "bismarcklaw.com",
        )


def test_rejects_existing_identity_conflict_and_duplicate_local_mapping():
    user = _user(
        "services@bismarcklaw.com",
        entra_tenant_id=ENTRA_TENANT,
        entra_object_id=STAFF_OID,
    )
    with pytest.raises(ValueError, match="Existing Entra link conflicts"):
        plan_links(
            [user], [_graph(OWNER_OID, user.email)], ENTRA_TENANT, "bismarcklaw.com"
        )

    first = _user("services@bismarcklaw.com")
    second = _user("alias@bismarcklaw.com")
    with pytest.raises(ValueError, match="multiple LawHand users"):
        plan_links(
            [first, second],
            [_graph(OWNER_OID, first.email, userPrincipalName=second.email)],
            ENTRA_TENANT,
            "bismarcklaw.com",
        )


def test_already_linked_is_idempotent():
    owner = _user(
        "services@bismarcklaw.com",
        entra_tenant_id=ENTRA_TENANT,
        entra_object_id=OWNER_OID,
    )
    plan = plan_links(
        [owner], [_graph(OWNER_OID, owner.email)], ENTRA_TENANT, "bismarcklaw.com"
    )
    assert plan["links"] == []
    assert plan["already_linked"][0]["user_id"] == str(owner.id)


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _Session:
    def __init__(self, tenant, users):
        self.tenant = tenant
        self.users = users
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, query):
        entity = query.column_descriptions[0]["entity"]
        return _Result([self.tenant] if entity is Tenant else self.users)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_repair_requires_reviewed_digest_before_writing(monkeypatch):
    tenant = Tenant(id=uuid.uuid4(), domain="bismarcklaw.com", name="Bismarck")
    owner = _user("services@bismarcklaw.com", tenant_id=tenant.id)
    session = _Session(tenant, [owner])
    monkeypatch.setattr(repair_script, "async_session_maker", lambda: session)
    monkeypatch.setattr(repair_script, "set_tenant_context", AsyncMock())
    token = jwt.encode({"tid": ENTRA_TENANT}, "test-key", algorithm="HS256")
    monkeypatch.setattr(repair_script, "get_fresh_token", AsyncMock(return_value=token))
    monkeypatch.setattr(
        repair_script,
        "_graph_users",
        AsyncMock(return_value=[_graph(OWNER_OID, owner.email)]),
    )

    arguments = {"tenant_id": str(tenant.id), "entra_tenant_id": ENTRA_TENANT}
    preview = await repair_script.repair(**arguments)
    assert preview["links"][0]["email"] == owner.email
    assert owner.entra_object_id is None
    assert session.rollbacks == 1

    with pytest.raises(ValueError, match="Plan changed"):
        await repair_script.repair(**arguments, confirmation="wrong")
    assert owner.entra_object_id is None

    applied = await repair_script.repair(
        **arguments, confirmation=preview["plan_sha256"]
    )
    assert applied["applied"] is True
    assert owner.entra_tenant_id == ENTRA_TENANT
    assert owner.entra_object_id == OWNER_OID
    assert owner.oauth_subject == "old-pairwise-subject"


@pytest.mark.asyncio
async def test_repair_rejects_wrong_connected_directory(monkeypatch):
    tenant = Tenant(id=uuid.uuid4(), domain="bismarcklaw.com", name="Bismarck")
    session = _Session(tenant, [_user("services@bismarcklaw.com")])
    monkeypatch.setattr(repair_script, "async_session_maker", lambda: session)
    monkeypatch.setattr(repair_script, "set_tenant_context", AsyncMock())
    wrong_token = jwt.encode(
        {"tid": "99999999-9999-4999-8999-999999999999"},
        "test-key",
        algorithm="HS256",
    )
    monkeypatch.setattr(
        repair_script, "get_fresh_token", AsyncMock(return_value=wrong_token)
    )
    graph_call = AsyncMock()
    monkeypatch.setattr(repair_script, "_graph_users", graph_call)

    with pytest.raises(ValueError, match="differs from expected"):
        await repair_script.repair(
            tenant_id=str(tenant.id), entra_tenant_id=ENTRA_TENANT
        )
    graph_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_can_use_reviewed_entra_export_when_token_is_unavailable(
    monkeypatch, tmp_path
):
    tenant = Tenant(id=uuid.uuid4(), domain="bismarcklaw.com", name="Bismarck")
    owner = _user("services@bismarcklaw.com", tenant_id=tenant.id)
    session = _Session(tenant, [owner])
    monkeypatch.setattr(repair_script, "async_session_maker", lambda: session)
    monkeypatch.setattr(repair_script, "set_tenant_context", AsyncMock())
    token_call = AsyncMock()
    monkeypatch.setattr(repair_script, "get_fresh_token", token_call)
    export = tmp_path / "entra-users.json"
    export.write_text(
        json.dumps(
            {
                "entra_tenant_id": ENTRA_TENANT,
                "users": [_graph(OWNER_OID, owner.email)],
            }
        ),
        encoding="utf-8",
    )

    preview = await repair_script.repair(
        tenant_id=str(tenant.id),
        entra_tenant_id=ENTRA_TENANT,
        graph_export=export,
    )
    assert preview["source"] == "operator-supplied Entra export"
    assert preview["links"][0]["object_id"] == OWNER_OID
    token_call.assert_not_awaited()

    export.write_text(
        json.dumps({"entra_tenant_id": str(uuid.uuid4()), "users": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="different Entra tenant"):
        await repair_script.repair(
            tenant_id=str(tenant.id),
            entra_tenant_id=ENTRA_TENANT,
            graph_export=export,
        )


@pytest.mark.asyncio
async def test_graph_user_listing_paginates_and_rejects_other_hosts(monkeypatch):
    next_url = repair_script.GRAPH_USERS_URL + "?$skiptoken=page2"

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self):
            self.calls = []
            self.other_host = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if len(self.calls) == 1:
                return Response(
                    {
                        "value": [_graph(OWNER_OID, "services@bismarcklaw.com")],
                        "@odata.nextLink": (
                            "https://elsewhere.example/users"
                            if self.other_host
                            else next_url
                        ),
                    }
                )
            return Response({"value": [_graph(STAFF_OID, "staff@bismarcklaw.com")]})

    client = Client()
    monkeypatch.setattr(repair_script.httpx, "AsyncClient", lambda **_kw: client)
    users = await repair_script._graph_users("test-token")
    assert len(users) == 2
    assert client.calls[1][0] == next_url
    assert client.calls[1][1]["params"] is None

    client.calls.clear()
    client.other_host = True
    with pytest.raises(ValueError, match="Unexpected Graph pagination URL"):
        await repair_script._graph_users("test-token")
