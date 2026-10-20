"""Real SQLite persistence and mocked Celery/platform boundaries; no credentials/network."""
import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

os.environ['UPLOADER_DB_URL'] = 'sqlite+aiosqlite:///:memory:'

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.exc import IntegrityError

from src.db import session as db
from src.db.models import UploaderTask
from src.db.repository import TaskRepository
from src.upload import service as svc
from src.upload import router as api
from src.upload.schemas import PublishTaskItem
from src.tasks.publish import publish_video_task


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path}/tasks.db')
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, 'engine', engine)
    monkeypatch.setattr(svc, 'AsyncSessionLocal', sessions)
    await db.init_db()
    service = svc.UploaderService()
    monkeypatch.setattr(service, 'check_cookie_valid', AsyncMock(return_value=True))
    monkeypatch.setattr(service, 'get_account', AsyncMock(return_value={'cookie_file': 'test'}))
    monkeypatch.setattr(service, '_get_cookie_file_path', lambda _: Path('mock-cookie'))
    monkeypatch.setattr(svc, '_resolve_publish_video_path', lambda _: Path('mock-video'))
    monkeypatch.setattr(service, '_run_publish', AsyncMock())
    queue = Mock()
    monkeypatch.setattr(api.publish_video_task, 'delay', queue)
    yield service, sessions, queue
    await engine.dispose()


def request(platform='douyin'):
    return api.PublishRequest(platform=platform, account_id='1', video_id='test.mp4', title='test', tags=['tag'])


@pytest.mark.asyncio
@pytest.mark.parametrize('platform', ['douyin', 'tencent', 'xhs'])
async def test_api_worker_query_and_duplicate_delivery(env, platform):
    service, sessions, queue = env
    response = await api.publish(request(platform), service)
    task_id = response.task_id
    kwargs = queue.call_args.kwargs
    assert kwargs['task_id'] == task_id and len(task_id) == 32
    item = PublishTaskItem(**await service.get_publish_task(task_id))
    assert item.task_id == task_id and item.account_id == '1'
    async with sessions() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        assert isinstance(task.id, int) and task.task_id == task_id
    # Exercise actual Celery task wrapper with eager execution, without Redis.
    from src.tasks import publish as worker
    original = worker.UploaderService
    worker.UploaderService = lambda: service
    try:
        await asyncio.to_thread(lambda: publish_video_task.apply(kwargs=kwargs, throw=True).get())
        await asyncio.to_thread(lambda: publish_video_task.apply(kwargs=kwargs, throw=True).get())
    finally:
        worker.UploaderService = original
    assert (await service.get_publish_task(task_id))['status'] == 'success'
    assert (await api.list_publish_tasks(service)).items[0].task_id == task_id
    service._run_publish.assert_awaited_once()
    with pytest.raises(api.HTTPException) as error:
        await api.retry_publish_task(task_id, service)
    assert error.value.status_code == 409
    assert queue.call_count == 1


@pytest.mark.asyncio
async def test_failure_retry_and_stale_attempt(env):
    service, _, queue = env
    task_id = (await api.publish(request(), service)).task_id
    first = queue.call_args.kwargs.copy()
    service._run_publish.side_effect = RuntimeError('mock failure')
    await service.execute_publish_task(**first)
    task = await service.get_publish_task(task_id)
    assert task['status'] == 'failed' and task['error_msg'] == 'mock failure'
    await api.retry_publish_task(task_id, service)
    retry = queue.call_args.kwargs.copy()
    assert retry['task_id'] == task_id and retry['attempt'] == 1
    await service.execute_publish_task(**first)  # delayed/redelivered old attempt
    assert service._run_publish.await_count == 1
    service._run_publish.side_effect = None
    await service.execute_publish_task(**retry)
    task = await service.get_publish_task(task_id)
    assert task['status'] == 'success' and task['retry_count'] == 1
    assert task['error_msg'] is None and task['finished_at']


@pytest.mark.asyncio
async def test_atomic_claim_and_retry_reservation(env):
    service, sessions, _ = env
    task_id = (await api.publish(request(), service)).task_id
    async def claim():
        async with sessions() as session:
            result = await TaskRepository(session).claim(task_id)
            await session.commit()
            return result
    assert sorted(await asyncio.gather(claim(), claim())) == [False, True]
    await service.update_publish_task_status(task_id, 'failed', 'failure')
    assert sorted(await asyncio.gather(
        service.reserve_publish_retry(task_id, 0), service.reserve_publish_retry(task_id, 0)
    )) == [False, True]


@pytest.mark.asyncio
async def test_missing_task_and_preflight_failure(env):
    service, _, queue = env
    kwargs = dict(task_id=uuid4().hex, platform='douyin', account_id='1', video_id='x', title='x', tags=[])
    await service.execute_publish_task(**kwargs)
    service._run_publish.assert_not_awaited()
    task_id = (await api.publish(request(), service)).task_id
    service.get_account.side_effect = ValueError('account missing')
    await service.execute_publish_task(**queue.call_args.kwargs)
    assert (await service.get_publish_task(task_id))['status'] == 'failed'
    service._run_publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_write_failure_does_not_enable_retry(env):
    service, _, queue = env
    task_id = (await api.publish(request(), service)).task_id
    service.update_publish_task_status = AsyncMock(side_effect=RuntimeError('database unavailable'))
    with pytest.raises(RuntimeError):
        await service.execute_publish_task(**queue.call_args.kwargs)
    assert (await service.get_publish_task(task_id))['status'] == 'running'
    await service.execute_publish_task(**queue.call_args.kwargs)
    service._run_publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_schema_migration_preserves_rows(env):
    service, sessions, _ = env
    # Build an old table from actual schema, without UUID column/index.
    async with db.engine.begin() as conn:
        await conn.execute(text('DROP TABLE uploader_tasks'))
        from sqlalchemy.schema import CreateTable
        from sqlalchemy.dialects.sqlite import dialect
        ddl = str(CreateTable(UploaderTask.__table__).compile(dialect=dialect()))
        ddl = '\n'.join(line for line in ddl.splitlines() if 'task_id' not in line)
        ddl = ddl.replace('FOREIGN KEY(account_id) REFERENCES accounts (id),', 'FOREIGN KEY(account_id) REFERENCES accounts (id)')
        await conn.execute(text(ddl))
        await conn.execute(text("INSERT INTO uploader_tasks (id,platform,video_id,title,status,retry_count,created_at,updated_at) VALUES (7,'xhs','old.mp4','old','failed',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    await db.init_db()
    await db.init_db()
    task = await service.get_publish_task('7')
    assert task['id'] == 7 and task['task_id'] == '7'
    PublishTaskItem(**task)
    async with sessions() as session:
        repo = TaskRepository(session)
        assert await repo.claim('7') is False
        assert await repo.reserve_retry('7', 0)
        assert await repo.claim('7', 1)
        assert await repo.set_success('7')
        await session.commit()
    assert (await service.get_publish_task('7'))['status'] == 'success'
    assert await service.get_publish_task(uuid4().hex) is None


@pytest.mark.asyncio
async def test_unique_uuid_and_numeric_uuid_do_not_alias_legacy(env):
    service, sessions, _ = env
    task_id = '1' * 32
    data = dict(task_id=task_id, platform='douyin', video_id='x')
    await service.create_publish_task(data)
    async with sessions() as session:
        assert (await TaskRepository(session).get_by_id(task_id)).task_id == task_id
        assert await TaskRepository(session).get_by_id('1') is None
    with pytest.raises(IntegrityError):
        await service.create_publish_task(data)


@pytest.mark.asyncio
@pytest.mark.parametrize('setup_name', ['douyin_setup', 'weixin_setup', 'xiaohongshu_setup'])
async def test_invalid_cookie_is_failure(monkeypatch, setup_name):
    monkeypatch.setattr(svc, setup_name, AsyncMock(return_value=False))
    platform = {'douyin_setup': 'douyin', 'weixin_setup': 'tencent', 'xiaohongshu_setup': 'xhs'}[setup_name]
    with pytest.raises(ValueError, match='登录已失效'):
        await svc.UploaderService()._run_publish(platform, 'mock-cookie', 'mock-video', 'title', [])


@pytest.mark.asyncio
async def test_http_response_contract_and_retry_errors(env):
    import httpx
    from fastapi import FastAPI
    service, _, queue = env
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_uploader_service] = lambda: service
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/uploader/publish', json=request().model_dump())
        assert response.status_code == 200
        task_id = response.json()['task_id']
        assert (await client.get(f'/uploader/publish/tasks/{task_id}')).json()['task_id'] == task_id
        assert (await client.get('/uploader/publish/tasks')).json()['items'][0]['task_id'] == task_id
        assert (await client.get('/uploader/publish/tasks/missing')).status_code == 404
        assert (await client.post(f'/uploader/publish/tasks/{task_id}/retry')).status_code == 409
        assert queue.call_count == 1
        service.check_cookie_valid.return_value = False
        assert (await client.post('/uploader/publish', json=request().model_dump())).status_code == 409


@pytest.mark.asyncio
async def test_queue_failure_retains_id_and_does_not_enable_duplicate_retry(env):
    service, _, queue = env
    queue.side_effect = ConnectionError('broker unavailable')
    with pytest.raises(api.HTTPException) as error:
        await api.publish(request(), service)
    assert error.value.status_code == 503
    task_id = error.value.detail['task_id']
    assert (await service.get_publish_task(task_id))['status'] == 'pending'
    with pytest.raises(api.HTTPException) as retry_error:
        await api.retry_publish_task(task_id, service)
    assert retry_error.value.status_code == 409
    # Ambiguous send was actually delivered: it can still execute once.
    await service.execute_publish_task(**queue.call_args.kwargs)
    service._run_publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_repository_updates_use_uuid(env):
    service, sessions, _ = env
    task_id = (await api.publish(request(), service)).task_id
    async with sessions() as session:
        repo = TaskRepository(session)
        assert await repo.set_running(task_id)
        assert await repo.set_failed(task_id, 'failed')
        assert await repo.update_request_data(task_id, {'test': True})
        assert await repo.increment_retry(task_id) == 1
        assert await repo.set_success(task_id)
        await session.commit()
    task = await service.get_publish_task(task_id)
    assert task['status'] == 'success' and task['request_data'] == {'test': True}


@pytest.mark.asyncio
@pytest.mark.parametrize('platform,setup,constructor', [
    ('douyin', 'douyin_setup', 'DouYinVideo'),
    ('tencent', 'weixin_setup', 'TencentVideo'),
    ('xhs', 'xiaohongshu_setup', 'XiaoHongShuVideo'),
])
async def test_platform_dispatch_and_options_are_preserved(monkeypatch, platform, setup, constructor):
    monkeypatch.setattr(svc, setup, AsyncMock(return_value=True))
    publisher = Mock(main=AsyncMock())
    factory = Mock(return_value=publisher)
    monkeypatch.setattr(svc, constructor, factory)
    await svc.UploaderService()._run_publish(
        platform, 'cookie', 'video', 'title', ['tag'], category='test-category',
        is_draft=True, short_title='short', declare_original=True,
        thumbnail_path='thumb', product_link='link', product_title='product',
        desc='body', cover_path='cover', is_private=True,
        publish_date='2026-11-01T12:00:00',
    )
    publisher.main.assert_awaited_once()
    args, kwargs = factory.call_args
    assert args[:3] == ('title', 'video', ['tag']) and args[4] == 'cookie'
    assert args[3].isoformat() == '2026-11-01T12:00:00'
    if platform == 'douyin':
        assert kwargs == dict(thumbnail_path='thumb', productLink='link', productTitle='product')
    elif platform == 'tencent':
        assert kwargs == dict(category='test-category', is_draft=True, short_title='short', declare_original=True)
    else:
        assert kwargs == dict(thumbnail_path='cover', desc='body', is_private=True)


@pytest.mark.asyncio
async def test_reinitialization_preserves_running_task(env):
    service, sessions, _ = env
    task_id = (await api.publish(request(), service)).task_id
    async with sessions() as session:
        assert await TaskRepository(session).claim(task_id)
        await session.commit()
    await asyncio.gather(db.init_db(), db.init_db())
    assert (await service.get_publish_task(task_id))['status'] == 'running'
