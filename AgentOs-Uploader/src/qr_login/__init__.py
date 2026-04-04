# -*- coding: utf-8 -*-
"""
二维码扫码登录服务
用于抖音、视频号、小红书等平台的扫码登录，自动获取 Cookie
"""

import asyncio
import logging
import os
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from src.config import settings
from src.config_manager import config_manager
from src.utils.playwright_net import (
    merge_chromium_launch_options,
    goto_with_retry,
    user_friendly_uploader_error,
    platform_label_for_error,
)
from src.config import settings
from src.utils.base_social_media import set_init_script
from src.utils.douyin_speed_routes import attach_douyin_speed_routes
from playwright.async_api import async_playwright

from .models import LoginStatus, LoginTask
from .drivers import get_driver
from .success_detector import LoginSuccessDetector

logger = logging.getLogger(__name__)

# 平台与初始 URL 的映射
PLATFORM_URLS = {
    "douyin": "https://creator.douyin.com/",
    "tencent": "https://channels.weixin.qq.com/login.html",
    "xhs": "https://creator.xiaohongshu.com/",
}


class QRLoginService:
    """二维码登录服务 (新驱动架构版)"""

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
        task.runner = asyncio.create_task(self._do_login_with_driver(task))

        return task

    async def _do_login_with_driver(self, task: LoginTask):
        """执行登录流程（驱动化重构版）"""
        playwright = None
        browser = None
        try:
            url = PLATFORM_URLS.get(task.platform)
            if not url:
                task.status = LoginStatus.FAILED
                task.error_msg = f"不支持的平台: {task.platform}"
                task.qr_ready.set()
                return

            # 1. 启动浏览器 (一键式任务不走池化，保持完全独立以保兼容)
            playwright = await async_playwright().start()
            launch_options = merge_chromium_launch_options({"headless": True})
            if settings.uploader_chrome_path:
                launch_options["executable_path"] = settings.uploader_chrome_path
            
            browser = await playwright.chromium.launch(**launch_options)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN"
            )
            context = await set_init_script(context)
            if task.platform == "douyin":
                await attach_douyin_speed_routes(context)

            page = await context.new_page()
            
            # 2. 导航
            await goto_with_retry(
                page, url, wait_until="domcontentloaded", log_label=f"task {task.id}"
            )
            
            # 3. 获取驱动
            driver = get_driver(task.platform)
            
            # 4. 准备与捕获二维码
            await driver.prepare_login_page(page)
            ok = await driver.capture_qr_code(page, task.qr_code_path)
            if not ok:
                raise RuntimeError("二维码捕获失败")
                
            task.qr_ready.set()
            logger.info(f"QR Ready for task {task.id}")

            # 5. 循环检测状态
            timeout = settings.get_platform_qr_validity(task.platform)
            for _ in range(timeout):
                # 检查状态
                if await LoginSuccessDetector.check(page, task.platform):
                    # 成功
                    task.user_name = await driver.get_user_name(page)
                    # 保存 Cookie
                    storage = await context.storage_state()
                    import json
                    cookie_filename = f"{uuid.uuid4().hex}.json"
                    dest = Path(settings.get_platform_cookies_path(task.platform)) / cookie_filename
                    os.makedirs(dest.parent, exist_ok=True)
                    with open(dest, "w", encoding="utf-8") as f:
                        json.dump(storage, f, ensure_ascii=False, indent=2)
                    
                    task.cookie_file = cookie_filename
                    task.status = LoginStatus.SUCCESS
                    logger.info(f"Task {task.id} login success: {task.user_name}")
                    return

                # 驱动检测扫码/过期状态
                scan_status = await driver.detect_scan_status(page)
                if scan_status == "scanning":
                    task.status = LoginStatus.SCANNING
                elif scan_status == "expired":
                    task.status = LoginStatus.FAILED
                    task.error_msg = "二维码已过期"
                    return

                await asyncio.sleep(2)

            task.status = LoginStatus.FAILED
            task.error_msg = "登录超时"

        except asyncio.CancelledError:
            task.status = LoginStatus.FAILED
            task.error_msg = "用户取消"
            task.qr_ready.set()
            raise
        except Exception as e:
            logger.error(f"Error in task {task.id}: {e}")
            task.status = LoginStatus.FAILED
            task.error_msg = user_friendly_uploader_error(e, platform_label_for_error(task.platform))
            task.qr_ready.set()
        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
            task.updated_at = datetime.now()

    def get_task(self, task_id: str) -> Optional[LoginTask]:
        """获取任务状态"""
        return self.tasks.get(task_id)

    async def get_qr_code_data(self, task_id: str) -> Optional[bytes]:
        """获取二维码图片数据"""
        task = self.tasks.get(task_id)
        if not task:
            return None

        try:
            await asyncio.wait_for(task.qr_ready.wait(), timeout=120)
        except asyncio.TimeoutError:
            return None

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
            if task.runner and not task.runner.done():
                task.runner.cancel()
            if task.qr_code_path and os.path.exists(task.qr_code_path):
                try:
                    os.remove(task.qr_code_path)
                except OSError:
                    pass


_qr_login_service: Optional[QRLoginService] = None


def get_qr_login_service() -> QRLoginService:
    global _qr_login_service
    if _qr_login_service is None:
        _qr_login_service = QRLoginService()
    return _qr_login_service


__all__ = [
    "LoginStatus",
    "LoginTask",
    "QRLoginService",
    "get_qr_login_service",
]
