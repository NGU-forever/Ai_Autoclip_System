# -*- coding: utf-8 -*-
"""
二维码扫码登录服务
用于抖音、视频号、小红书等平台的扫码登录，自动获取 Cookie
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from src.config import settings

from .models import LoginStatus, LoginTask
from .douyin import DouyinLogin
from .tencent import TencentLogin
from .xhs import XHSLogin

logger = logging.getLogger(__name__)

# 平台注册表
PLATFORM_REGISTRY = {
    "douyin": DouyinLogin,
    "tencent": TencentLogin,
    "xhs": XHSLogin,
}


class QRLoginService:
    """二维码登录服务"""

    def __init__(self):
        self.tasks: Dict[str, LoginTask] = {}
        self._cleanup_old_tasks()

    def _cleanup_old_tasks(self):
        """清理超过30分钟的旧任务"""
        now = datetime.now()
        expired = [
            tid for tid, task in self.tasks.items()
            if (now - task.created_at).total_seconds() > 1800
        ]
        for tid in expired:
            del self.tasks[tid]

    def _ensure_dirs(self):
        """确保目录存在"""
        os.makedirs(settings.uploader_cookies_path, exist_ok=True)
        qr_dir = Path(settings.storage_root) / "uploader" / "qr_codes"
        os.makedirs(qr_dir, exist_ok=True)
        return qr_dir

    async def start_login(self, platform: str) -> LoginTask:
        """开始扫码登录流程"""
        task_id = str(uuid.uuid4())
        qr_dir = self._ensure_dirs()

        task = LoginTask(
            id=task_id,
            platform=platform,
            status=LoginStatus.PENDING,
            qr_code_path=str(qr_dir / f"{task_id}.png")
        )
        self.tasks[task_id] = task

        # 启动异步任务执行登录流程
        logger.info(f"Starting login task {task_id} for platform {platform}")
        task.runner = asyncio.create_task(self._do_login(task))

        return task

    async def _do_login(self, task: LoginTask):
        """执行登录流程（在后台运行）"""
        try:
            if task.platform not in PLATFORM_REGISTRY:
                task.status = LoginStatus.FAILED
                task.error_msg = f"不支持的平台: {task.platform}"
                task.qr_ready.set()
                return

            # 获取对应平台的登录类并执行
            login_class = PLATFORM_REGISTRY[task.platform]
            login_instance = login_class()
            await login_instance.login(task)

        except asyncio.CancelledError:
            task.status = LoginStatus.FAILED
            if not task.error_msg:
                task.error_msg = "用户取消"
            task.qr_ready.set()
            logger.info("QR login task %s cancelled", task.id)
            raise
        except Exception as e:
            logger.error(f"Error in QR login for {task.platform}: {str(e)}")
            task.status = LoginStatus.FAILED
            # 如果错误信息还没有被设置，使用通用错误处理
            if not task.error_msg:
                from uploader.utils.playwright_net import (
                    user_friendly_uploader_error,
                    platform_label_for_error,
                )
                task.error_msg = user_friendly_uploader_error(
                    e, platform_label_for_error(task.platform)
                )
            task.qr_ready.set()
        finally:
            task.updated_at = datetime.now()

    def get_task(self, task_id: str) -> Optional[LoginTask]:
        """获取任务状态"""
        return self.tasks.get(task_id)

    async def get_qr_code_data(self, task_id: str) -> Optional[bytes]:
        """获取二维码图片数据。使用 asyncio.Event 等待后台任务完成截图，零延迟通知。"""
        task = self.tasks.get(task_id)
        if not task:
            return None

        # 等待后台 Playwright 任务完成 QR 截图（event.set()），最多等 120 秒
        try:
            await asyncio.wait_for(task.qr_ready.wait(), timeout=120)
        except asyncio.TimeoutError:
            logger.warning(f"QR ready timeout for task {task_id}")
            return None

        # Event 已 set，读取文件
        p = task.qr_code_path
        if p and os.path.exists(p) and os.path.getsize(p) >= 200:
            try:
                with open(p, "rb") as f:
                    return f.read()
            except OSError:
                pass

        return None

    def cancel_task(self, task_id: str):
        """取消登录任务"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = LoginStatus.FAILED
            task.error_msg = "用户取消"
            task.qr_ready.set()
            runner = task.runner
            if runner is not None and not runner.done():
                runner.cancel()
            # 清理二维码文件
            if task.qr_code_path and os.path.exists(task.qr_code_path):
                try:
                    os.remove(task.qr_code_path)
                except OSError:
                    pass


# 全局服务实例
_qr_login_service: Optional[QRLoginService] = None


def get_qr_login_service() -> QRLoginService:
    """获取扫码登录服务实例（单例）"""
    global _qr_login_service
    if _qr_login_service is None:
        _qr_login_service = QRLoginService()
    return _qr_login_service


# 导出公共 API
__all__ = [
    "LoginStatus",
    "LoginTask",
    "QRLoginService",
    "get_qr_login_service",
    "DouyinLogin",
    "TencentLogin",
    "XHSLogin",
    "PLATFORM_REGISTRY",
]
