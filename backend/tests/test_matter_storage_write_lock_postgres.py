"""Cloud upload guards permit FK references but still exclude cutover writes."""

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import set_tenant_context
from app.models.tenant import Tenant, TenantSettings
from app.services.matter_file_store import MatterFileStoragePolicyError, MatterFileStore


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["cutover_lock", "tenant_update"])
async def test_cloud_write_guard_still_excludes_cutover(
    test_engine, db_session, test_tenant, operation
):
    tenant_id = test_tenant.id
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    statement = (
        select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
        if operation == "cutover_lock"
        else update(Tenant)
        .where(Tenant.id == tenant_id)
        .values(cloud_root_folder="replacement-root")
    )
    async with factory() as storage:
        await MatterFileStore()._lock_write_binding(
            storage, str(tenant_id), None, "onedrive", None
        )
        await set_tenant_context(db_session, str(tenant_id))
        await db_session.execute(text("SET LOCAL lock_timeout = '100ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            await db_session.execute(statement)
        await db_session.rollback()
        await storage.rollback()

    # The same operation succeeds once the uploader releases its binding lock.
    await set_tenant_context(db_session, str(tenant_id))
    await db_session.execute(statement)
    await db_session.rollback()


@pytest.mark.asyncio
async def test_waiting_upload_rechecks_provider_after_cutover(
    test_engine, db_session, test_tenant
):
    tenant_id = test_tenant.id
    db_session.add(
        TenantSettings(tenant_id=tenant_id, primary_cloud_provider="onedrive")
    )
    await db_session.commit()
    await set_tenant_context(db_session, str(tenant_id))
    await db_session.execute(
        select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
    )
    await db_session.execute(
        update(TenantSettings)
        .where(TenantSettings.tenant_id == tenant_id)
        .values(primary_cloud_provider="google_drive")
    )
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as storage:
        await set_tenant_context(storage, str(tenant_id))
        await storage.execute(text("SET LOCAL lock_timeout = '100ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            await MatterFileStore()._lock_write_binding(
                storage, str(tenant_id), None, "onedrive", None
            )
        await storage.rollback()
        await db_session.commit()
        with pytest.raises(MatterFileStoragePolicyError, match="provider changed"):
            await MatterFileStore()._lock_write_binding(
                storage, str(tenant_id), None, "onedrive", None
            )
