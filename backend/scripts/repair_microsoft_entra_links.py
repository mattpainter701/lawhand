"""One-time repair of existing users after a Microsoft app registration change.

Run from ``backend`` with the target LawHand tenant and its verified Entra
directory ID. A dry run prints the proposed links and a confirmation digest.
Applying requires that exact digest so an operator reviews every mapping.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import uuid
from collections import defaultdict
from pathlib import Path

import httpx
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy import select

from app.database import async_session_maker, set_tenant_context
from app.models.tenant import Tenant
from app.models.user import User
from app.services.token_vault import get_fresh_token

GRAPH_USERS_URL = "https://graph.microsoft.com/v1.0/users"


def _uuid(value: str) -> str:
    return str(uuid.UUID(str(value)))


def plan_links(
    users: list[User], graph_users: list[dict], entra_tenant_id: str, email_domain: str
) -> dict:
    """Match a trusted Graph directory snapshot to existing, active users only."""
    entra_tenant_id = _uuid(entra_tenant_id)
    by_address: dict[str, set[str]] = defaultdict(set)
    for entry in graph_users:
        if entry.get("accountEnabled") is False or entry.get("userType") == "Guest":
            continue
        object_id = _uuid(entry["id"])
        for field in ("mail", "userPrincipalName"):
            address = (entry.get(field) or "").strip().lower()
            if address:
                by_address[address].add(object_id)

    links = []
    already_linked = []
    skipped = []
    owner_by_object: dict[str, str] = {}
    for user in sorted(users, key=lambda row: (row.email.lower(), str(row.id))):
        address = user.email.strip().lower()
        if not address.endswith("@" + email_domain.lower()):
            skipped.append({"email": user.email, "reason": "outside tenant domain"})
            continue
        objects = by_address.get(address, set())
        if not objects:
            skipped.append(
                {"email": user.email, "reason": "not in enabled Graph users"}
            )
            continue
        if len(objects) != 1:
            raise ValueError(f"Ambiguous Graph identity for {user.email}")
        if not user.is_active or user.principal_type != "human":
            skipped.append(
                {"email": user.email, "reason": "inactive or service principal"}
            )
            continue
        if user.oauth_provider not in (None, "microsoft"):
            skipped.append({"email": user.email, "reason": "another OAuth provider"})
            continue

        object_id = next(iter(objects))
        previous_owner = owner_by_object.setdefault(object_id, str(user.id))
        if previous_owner != str(user.id):
            raise ValueError(
                f"Graph object maps to multiple LawHand users: {object_id}"
            )
        if (user.entra_tenant_id or user.entra_object_id) and (
            user.entra_tenant_id != entra_tenant_id or user.entra_object_id != object_id
        ):
            raise ValueError(f"Existing Entra link conflicts for {user.email}")

        item = {"user_id": str(user.id), "email": user.email, "object_id": object_id}
        if user.entra_tenant_id and user.entra_object_id:
            already_linked.append(item)
        else:
            links.append(item)

    return {"links": links, "already_linked": already_linked, "skipped": skipped}


async def _graph_users(access_token: str) -> list[dict]:
    users: list[dict] = []
    url: str | None = GRAPH_USERS_URL
    async with httpx.AsyncClient(timeout=30) as client:
        while url:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=(
                    {
                        "$select": "id,mail,userPrincipalName,accountEnabled,userType",
                        "$top": 200,
                    }
                    if url == GRAPH_USERS_URL
                    else None
                ),
            )
            response.raise_for_status()
            payload = response.json()
            users.extend(payload.get("value", []))
            next_url = payload.get("@odata.nextLink")
            if next_url and not next_url.startswith(GRAPH_USERS_URL + "?"):
                raise ValueError("Unexpected Graph pagination URL")
            url = next_url
    return users


async def repair(
    *,
    tenant_id: str,
    entra_tenant_id: str,
    confirmation: str | None = None,
    graph_export: Path | None = None,
) -> dict:
    tenant_id = _uuid(tenant_id)
    entra_tenant_id = _uuid(entra_tenant_id)
    async with async_session_maker() as db:
        await set_tenant_context(db, tenant_id)
        tenant = (
            await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
        ).scalar_one_or_none()
        if tenant is None:
            raise ValueError("LawHand tenant not found")

        if graph_export is None:
            token = await get_fresh_token(db, tenant_id, "microsoft")
            if not token:
                raise ValueError(
                    "No usable Microsoft directory connection for this tenant"
                )
            # A refresh can rotate the stored refresh token; preserve that rotation.
            await db.commit()
            try:
                token_tenant = _uuid(jwt.get_unverified_claims(token)["tid"])
            except (KeyError, ValueError, TypeError, JWTError) as exc:
                raise ValueError(
                    "Microsoft Graph access token has no tenant ID"
                ) from exc
            if token_tenant != entra_tenant_id:
                raise ValueError(
                    "Connected Microsoft directory differs from expected Entra tenant"
                )
            # Graph validates this access token. Browser claims are never used.
            graph_users = await _graph_users(token)
            source = "connected Graph directory"
        else:
            # Use only an export obtained by an operator from the named Entra
            # directory. This path works if the old app's refresh token expired.
            export = json.loads(graph_export.read_text(encoding="utf-8"))
            if _uuid(export["entra_tenant_id"]) != entra_tenant_id:
                raise ValueError("Export belongs to a different Entra tenant")
            graph_users = export["users"]
            if not isinstance(graph_users, list):
                raise ValueError("Export users must be a list")
            source = "operator-supplied Entra export"
        await set_tenant_context(db, tenant_id)
        users = list(
            (
                await db.execute(
                    select(User).where(User.tenant_id == tenant.id).with_for_update()
                )
            )
            .scalars()
            .all()
        )
        plan = plan_links(users, graph_users, entra_tenant_id, tenant.domain)
        material = {
            "tenant_id": tenant_id,
            "entra_tenant_id": entra_tenant_id,
            "links": plan["links"],
        }
        digest = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        result = {
            "tenant_id": tenant_id,
            "domain": tenant.domain,
            "entra_tenant_id": entra_tenant_id,
            "source": source,
            "graph_user_count": len(graph_users),
            "plan_sha256": digest,
            **plan,
            "applied": False,
        }
        if confirmation is None:
            await db.rollback()
            return result
        if confirmation != digest:
            raise ValueError("Plan changed since review; rerun the dry run")

        by_id = {str(user.id): user for user in users}
        for item in plan["links"]:
            user = by_id[item["user_id"]]
            user.entra_tenant_id = entra_tenant_id
            user.entra_object_id = item["object_id"]
            user.oauth_provider = "microsoft"
            # Keep the old subject until the next successful callback replaces it.
        await db.commit()
        result["applied"] = True
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, help="LawHand tenant UUID")
    parser.add_argument(
        "--entra-tenant-id", required=True, help="Verified Entra directory UUID"
    )
    parser.add_argument(
        "--graph-export",
        type=Path,
        help="Trusted Entra directory JSON export when the connection token is unavailable",
    )
    parser.add_argument(
        "--confirm-plan-sha256",
        help="Apply exactly the mapping printed by a preceding dry run",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(
        json.dumps(
            asyncio.run(
                repair(
                    tenant_id=args.tenant_id,
                    entra_tenant_id=args.entra_tenant_id,
                    confirmation=args.confirm_plan_sha256,
                    graph_export=args.graph_export,
                )
            ),
            indent=2,
        )
    )
