import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import matter_file_store as module
from app.services.matter_file_store import MatterFileStore, MatterFileStoragePolicyError


@pytest.mark.asyncio
async def test_upload_waits_for_provisioned_binding(monkeypatch):
    ready = {'_status': 'provisioned', 'google_drive': {'matter_folder_id': 'one-matter'}}
    db = Mock(execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=ready))))
    pause = AsyncMock()
    monkeypatch.setattr(module.asyncio, 'sleep', pause)
    result = await MatterFileStore()._ready_cloud_binding(db, str(uuid.uuid4()), 'case', {'_status': 'provisioning'})
    assert result == ready
    pause.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['failed', 'provisioning'])
async def test_failed_or_stalled_provision_does_not_start_an_upload(monkeypatch, status):
    pending = {'_status': status}
    db = Mock(execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=pending))))
    monkeypatch.setattr(module.asyncio, 'sleep', AsyncMock())
    with pytest.raises(MatterFileStoragePolicyError) as exc_info:
        await MatterFileStore().store_matter_file_result(db, str(uuid.uuid4()), 'case', 'documents', 'a.pdf', b'file', 'application/pdf', matter_cloud_folder=pending)
    message = str(exc_info.value)
    assert "Documents > Document tools" in message
    assert "No file was stored" in message
    if status == 'failed':
        assert "setup failed" in message
    else:
        assert "still being prepared" in message


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['onedrive', 'google_drive'])
@pytest.mark.parametrize('require_cloud', [False, True])
async def test_missing_binding_returns_setup_action_without_fallback(
    monkeypatch, provider, require_cloud
):
    store = MatterFileStore()
    tenant_id = str(uuid.uuid4())
    if provider == 'onedrive':
        monkeypatch.setattr(module, 'get_fresh_token', AsyncMock(return_value='token'))
        configured = 'onedrive'
        label = 'OneDrive'
        path_traversal = AsyncMock(
            side_effect=AssertionError('must not create a slug-based folder tree')
        )
        monkeypatch.setattr(module, '_ensure_onedrive_path', path_traversal)
        monkeypatch.setattr(
            store,
            '_try_store_google_drive',
            AsyncMock(side_effect=AssertionError('must not try another provider')),
        )
        monkeypatch.setattr(
            store,
            '_try_store_sharepoint',
            AsyncMock(side_effect=AssertionError('must not try another provider')),
        )
    else:
        monkeypatch.setattr(module, '_storage_token', AsyncMock(return_value='token'))
        configured = 'google_drive'
        label = 'Google Drive'
        path_traversal = AsyncMock(
            side_effect=AssertionError('must not create a slug-based folder tree')
        )
        monkeypatch.setattr(module, '_ensure_gdrive_path', path_traversal)
        monkeypatch.setattr(
            store,
            '_try_store_onedrive',
            AsyncMock(side_effect=AssertionError('must not try another provider')),
        )
        monkeypatch.setattr(
            store,
            '_try_store_sharepoint',
            AsyncMock(side_effect=AssertionError('must not try another provider')),
        )
    monkeypatch.setattr(
        store,
        '_store_local',
        AsyncMock(side_effect=AssertionError('must not use local storage')),
    )

    kwargs = dict(
        db=object(),
        tenant_id=tenant_id,
        matter_slug='slug',
        category='documents',
        filename='file.pdf',
        content=b'x',
        content_type='application/pdf',
        matter_cloud_folder=None,
        preferred_provider=configured,
        require_cloud=require_cloud,
    )

    expected = (
        f"This matter's {label} folder is not set up. In Documents > Document tools, "
        'choose Set up folders, then retry. No file was stored.'
    )
    if require_cloud:
        result = await store.store_matter_file_result(**kwargs)
        assert result.error == expected
        assert result.error_code == 'matter_folder_not_provisioned'
        assert not result.succeeded
    else:
        with pytest.raises(MatterFileStoragePolicyError, match='Set up folders') as exc_info:
            await store.store_matter_file_result(**kwargs)
        assert str(exc_info.value) == expected
    path_traversal.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_onedrive_permission_failure_keeps_generic_closed_failure(
    monkeypatch,
):
    class ForbiddenResponse:
        status_code = 403
        text = 'Graph permission denied with provider details'

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def put(self, *_args, **_kwargs):
            return ForbiddenResponse()

    monkeypatch.setattr(module, 'get_fresh_token', AsyncMock(return_value='token'))
    monkeypatch.setattr(
        module, '_ensure_onedrive_path', AsyncMock(return_value='documents-folder')
    )
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **_kwargs: FakeClient())
    store = MatterFileStore()
    monkeypatch.setattr(
        store,
        '_try_store_google_drive',
        AsyncMock(side_effect=AssertionError('must not try another provider')),
    )
    monkeypatch.setattr(
        store,
        '_try_store_sharepoint',
        AsyncMock(side_effect=AssertionError('must not try another provider')),
    )
    monkeypatch.setattr(
        store,
        '_store_local',
        AsyncMock(side_effect=AssertionError('must not use local storage')),
    )

    with pytest.raises(MatterFileStoragePolicyError) as exc_info:
        await store.store_matter_file_result(
            db=object(),
            tenant_id=str(uuid.uuid4()),
            matter_slug='slug',
            category='documents',
            filename='file.pdf',
            content=b'x',
            content_type='application/pdf',
            matter_cloud_folder={'onedrive': {'matter_folder_id': 'matter-root'}},
            preferred_provider='onedrive',
        )

    message = str(exc_info.value)
    assert 'Configured Microsoft OneDrive storage is unavailable' in message
    assert 'Reconnect Microsoft OneDrive or verify its folder permissions' in message
    assert 'Graph permission denied' not in message
