# -*- coding: utf-8 -*-
"""
数据库 Repository 层
封装所有数据库 CRUD，对上层 Service 屏蔽 ORM 细节。
"""

import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Account, UploaderTask


# ─────────────────────────────────────────────────────────────────────────────
# Accounts
# ─────────────────────────────────────────────────────────────────────────────

class AccountRepository:

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        platform: str,
        account_name: str,
        cookie_file: str,
    ) -> Account:
        account = Account(
            id=str(uuid.uuid4()),
            platform=platform,
            account_name=account_name,
            cookie_file=cookie_file,
        )
        self._session.add(account)
        await self._session.flush()
        return account

    async def get_by_id(self, account_id: str) -> Optional[Account]:
        result = await self._session.execute(
            select(Account).where(Account.id == account_id)
        )
        return result.scalar_one_or_none()

    async def get_by_platform(self, platform: str) -> Optional[Account]:
        result = await self._session.execute(
            select(Account)
            .where(Account.platform == platform, Account.is_active.is_(True))
            .order_by(Account.created_at)
        )
        return result.scalars().first()

    async def get_by_platform_and_cookie(
        self, platform: str, cookie_file: str
    ) -> Optional[Account]:
        """根据平台和 cookie 文件查找账号"""
        result = await self._session.execute(
            select(Account)
            .where(
                Account.platform == platform,
                Account.cookie_file == cookie_file,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(self, account_id: str, is_active: bool) -> bool:
        """更新账号激活状态"""
        result = await self._session.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(is_active=is_active, updated_at=datetime.now())
        )
        return result.rowcount > 0

    async def list_by_platform(self, platform: str) -> List[Account]:
        result = await self._session.execute(
            select(Account)
            .where(Account.platform == platform, Account.is_active.is_(True))
            .order_by(Account.created_at)
        )
        return list(result.scalars().all())

    async def list_all(self) -> List[Account]:
        result = await self._session.execute(
            select(Account).where(Account.is_active.is_(True)).order_by(Account.platform)
        )
        return list(result.scalars().all())

    async def deactivate(self, account_id: str) -> bool:
        result = await self._session.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(is_active=False)
        )
        return result.rowcount > 0

    async def update_or_create_by_platform(
        self,
        platform: str,
        account_name: str,
        cookie_file: str,
    ) -> Account:
        """同一平台只保留一个活跃账号：更新现有或创建新账号。"""
        existing = await self.get_by_platform(platform)
        if existing:
            existing.account_name = account_name
            existing.cookie_file = cookie_file
            existing.is_active = True
            existing.updated_at = datetime.now()
            await self._session.flush()
            return existing
        new_account = Account(
            id=str(uuid.uuid4()),
            platform=platform,
            account_name=account_name,
            cookie_file=cookie_file,
        )
        self._session.add(new_account)
        await self._session.flush()
        return new_account


# ─────────────────────────────────────────────────────────────────────────────
# Uploader Tasks
# ─────────────────────────────────────────────────────────────────────────────

class TaskRepository:

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        task_id: str,
        platform: str,
        video_id: str,
        account_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        request_data: Optional[Dict[str, Any]] = None,
    ) -> UploaderTask:
        task = UploaderTask(
            id=task_id,
            platform=platform,
            account_id=account_id,
            video_id=video_id,
            title=title,
            description=description,
            tags=json.dumps(tags or [], ensure_ascii=False),
            request_data=json.dumps(request_data or {}, ensure_ascii=False),
            status="pending",
        )
        self._session.add(task)
        await self._session.flush()
        return task

    async def get_by_id(self, task_id: str) -> Optional[UploaderTask]:
        result = await self._session.execute(
            select(UploaderTask).where(UploaderTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_by_status(self, status: str) -> List[UploaderTask]:
        result = await self._session.execute(
            select(UploaderTask)
            .where(UploaderTask.status == status)
            .order_by(UploaderTask.created_at)
        )
        return list(result.scalars().all())

    async def list_all(self, limit: int = 100) -> List[UploaderTask]:
        result = await self._session.execute(
            select(UploaderTask).order_by(UploaderTask.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def set_running(self, task_id: str) -> bool:
        result = await self._session.execute(
            update(UploaderTask)
            .where(UploaderTask.id == task_id)
            .values(status="running", started_at=datetime.now())
        )
        return result.rowcount > 0

    async def set_success(self, task_id: str) -> bool:
        result = await self._session.execute(
            update(UploaderTask)
            .where(UploaderTask.id == task_id)
            .values(status="success", finished_at=datetime.now())
        )
        return result.rowcount > 0

    async def set_failed(self, task_id: str, error_msg: str) -> bool:
        result = await self._session.execute(
            update(UploaderTask)
            .where(UploaderTask.id == task_id)
            .values(
                status="failed",
                error_msg=error_msg,
                finished_at=datetime.now(),
            )
        )
        return result.rowcount > 0

    async def update_status(
        self,
        task_id: str,
        status: str,
        error_msg: Optional[str] = None,
    ) -> bool:
        values = {"status": status, "updated_at": datetime.now()}
        if error_msg is not None:
            values["error_msg"] = error_msg
        if status == "running":
            values["started_at"] = datetime.now()
        if status in ("success", "failed"):
            values["finished_at"] = datetime.now()
        result = await self._session.execute(
            update(UploaderTask).where(UploaderTask.id == task_id).values(**values)
        )
        return result.rowcount > 0

    async def update_request_data(self, task_id: str, request_data: Dict[str, Any]) -> bool:
        result = await self._session.execute(
            update(UploaderTask)
            .where(UploaderTask.id == task_id)
            .values(
                request_data=json.dumps(request_data, ensure_ascii=False),
                updated_at=datetime.now(),
            )
        )
        return result.rowcount > 0

    async def increment_retry(self, task_id: str) -> int:
        """递增重试次数并返回最新值"""
        task = await self.get_by_id(task_id)
        if not task:
            return 0
        new_count = task.retry_count + 1
        await self._session.execute(
            update(UploaderTask)
            .where(UploaderTask.id == task_id)
            .values(retry_count=new_count, status="pending")
        )
        return new_count

    async def reconcile_stale(self) -> int:
        """
        服务启动时调用：将所有 running 状态的任务重置为 failed
        （它们是上次进程崩溃时遗留的孤儿任务）。
        返回修复的任务数量。
        """
        result = await self._session.execute(
            update(UploaderTask)
            .where(UploaderTask.status == "running")
            .values(
                status="failed",
                error_msg="服务重启，任务中断",
                finished_at=datetime.now(),
            )
        )
        return result.rowcount
