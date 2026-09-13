"""Rename tenants' pre-rebrand root cloud folder to the current default.

Renames the provider-side display name of a tenant's OneDrive, SharePoint,
or Google Drive root folder from the legacy ``claritylegal-records`` to
``lawhand-records`` (``app.services.cloud_init.ROOT_FOLDER_NAME``). Folder
IDs are authoritative and are never touched, so matter folders and document
bindings are unaffected either way; this only relabels the root folder a
tenant sees in their own cloud storage.

Only tenants whose saved root binding still carries the legacy name are
touched — a firm that already renamed its root folder to something of its
own choosing is left alone. Safe to rerun: a tenant with nothing left to
rename is reported with no providers renamed.

Run without ``--apply`` first to see which tenants and providers would be
affected before making real changes to customer cloud storage.
"""

import argparse
import asyncio
import json

from sqlalchemy import select

from app.database import async_session_maker, set_tenant_context
from app.models.tenant import Tenant
from app.services.cloud_init import LEGACY_ROOT_FOLDER_NAME, rename_legacy_root_folder

PROVIDERS = ("onedrive", "sharepoint", "google_drive")


def _legacy_providers(cloud_root: object) -> list[str]:
    if not isinstance(cloud_root, dict):
        return []
    return [
        provider
        for provider in PROVIDERS
        if isinstance(cloud_root.get(provider), dict)
        and (cloud_root[provider].get("folder_name") or "").strip().lower()
        == LEGACY_ROOT_FOLDER_NAME
    ]


async def run(*, apply: bool) -> dict:
    async with async_session_maker() as db:
        rows = (
            await db.execute(select(Tenant.id, Tenant.name, Tenant.cloud_root_folder))
        ).all()

    candidates = [
        (tenant_id, name, _legacy_providers(cloud_root))
        for tenant_id, name, cloud_root in rows
        if _legacy_providers(cloud_root)
    ]

    tenants_report = []
    for tenant_id, name, legacy_providers in candidates:
        async with async_session_maker() as db:
            await set_tenant_context(db, str(tenant_id))
            if apply:
                renamed = await rename_legacy_root_folder(db, str(tenant_id))
                await db.commit()
            else:
                renamed = {}
                await db.rollback()
        tenants_report.append(
            {
                "tenant_id": str(tenant_id),
                "tenant_name": name,
                "legacy_providers": legacy_providers,
                "renamed_providers": sorted(renamed) if apply else None,
            }
        )

    return {
        "apply": apply,
        "candidate_count": len(candidates),
        "tenants": tenants_report,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the rename; omit for a read-only validation run.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    print(json.dumps(asyncio.run(run(apply=arguments.apply)), indent=2))
