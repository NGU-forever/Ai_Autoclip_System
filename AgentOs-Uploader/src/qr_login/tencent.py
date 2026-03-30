# -*- coding: utf-8 -*-
"""
视频号（腾讯）扫码登录实现
"""

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Dict

from playwright.async_api import async_playwright

from src.config import settings
from uploader.conf import LOCAL_CHROME_PATH
from uploader.utils.base_social_media import set_init_script
from uploader.utils.playwright_net import (
    goto_with_retry,
    merge_chromium_launch_options,
    user_friendly_uploader_error,
    platform_label_for_error,
)

from .base import BasePlatformLogin
from .models import LoginStatus

logger = logging.getLogger(__name__)


class TencentLogin(BasePlatformLogin):
    """视频号扫码登录"""

    def __init__(self):
        super().__init__("tencent")

    async def login(self, task) -> None:
        """执行视频号登录流程"""
        logger.info(f"Starting Tencent Video Channel login for task {task.id}")
        async with async_playwright() as playwright:
            launch_options = merge_chromium_launch_options({"headless": True})
            if LOCAL_CHROME_PATH:
                launch_options["executable_path"] = LOCAL_CHROME_PATH

            browser = await playwright.chromium.launch(**launch_options)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
            )
            context = await set_init_script(context)
            page = await context.new_page()

            try:
                # 直接进登录页，避免首页再跳转导致二维码区域延迟或 DOM 不一致
                login_url = "https://channels.weixin.qq.com/login.html"
                logger.info(f"Navigating to {login_url}")
                await goto_with_retry(
                    page,
                    login_url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                    retries=3,
                    delay_sec=2.5,
                    log_label=f"Tencent QR task {task.id} goto",
                )
                await asyncio.sleep(0.6)

                logger.info(f"Page loaded: {await page.title()} - {page.url}")

                ok = await self._capture_login_qr_fast(page, task.qr_code_path, "Tencent")
                png_ok = (
                    ok
                    and os.path.exists(task.qr_code_path)
                    and os.path.getsize(task.qr_code_path) >= 200
                )
                if png_ok:
                    logger.info(f"Screenshot saved to {task.qr_code_path}")
                    task.qr_ready.set()  # 通知等待方 QR 已就绪
                else:
                    logger.error(f"Failed to generate valid QR PNG at {task.qr_code_path}")
                    task.status = LoginStatus.FAILED
                    task.error_msg = "二维码生成失败"
                    task.qr_ready.set()  # 即使失败也要通知，避免永远阻塞
                    return

                logger.info("QR code generated, waiting for scan...")

                # 轮询检测登录状态（最多5分钟）
                scan_detected = False
                for i in range(300):
                    await asyncio.sleep(1)

                    # 检查是否已登录（使用多种 URL 模式匹配）
                    current_url = page.url
                    login_success_patterns = [
                        "platform/post/create",
                        "platform/post/list",
                        "#/platform",
                        "#/creator",
                        "channels.weixin.qq.com/platform",
                    ]
                    is_logged_in = any(pattern in current_url for pattern in login_success_patterns)

                    if is_logged_in and "login.html" not in current_url:
                        logger.info(f"Tencent login success detected, URL: {current_url}")
                        # 登录成功，保存到视频号目录
                        cookie_filename = f"{uuid.uuid4().hex}.json"
                        platform_cookies_path = Path(settings.get_platform_cookies_path("tencent"))
                        platform_cookies_path.mkdir(parents=True, exist_ok=True)
                        cookie_path = platform_cookies_path / cookie_filename
                        await context.storage_state(path=str(cookie_path))

                        task.status = LoginStatus.SUCCESS
                        task.cookie_file = cookie_filename
                        task.user_name = f"视频号_{task.id[:8]}"
                        break

                    # 检测已扫码状态（每隔 3 秒检查一次）
                    if not scan_detected and i % 3 == 0:
                        try:
                            page_text = await page.content()
                            scan_indicators = ['已扫码', '扫描成功', '请在手机上确认', '确认登录']
                            if any(ind in page_text for ind in scan_indicators):
                                scan_detected = True
                                task.status = LoginStatus.SCANNING
                                logger.info(f"Tencent QR code scanned, waiting for confirmation")
                        except:
                            pass
                else:
                    task.status = LoginStatus.EXPIRED
                    task.error_msg = "登录超时，请重试"

            except Exception as e:
                logger.error(f"Error in Tencent QR login: {str(e)}")
                task.status = LoginStatus.FAILED
                task.error_msg = user_friendly_uploader_error(
                    e, platform_label_for_error("tencent")
                )
                task.qr_ready.set()
            finally:
                await context.close()
                await browser.close()
