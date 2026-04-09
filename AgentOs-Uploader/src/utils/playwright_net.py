# -*- coding: utf-8 -*-
"""Playwright 网络：导航重试、用户可读错误信息。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)

# 与 _init_tencent 等保持一致，降低异常风控概率
DEFAULT_DESKTOP_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

CHROMIUM_EXTRA_LAUNCH_ARGS = (
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox"
)


def platform_label_for_error(platform: str) -> str:
    return {
        "douyin": "抖音创作者",
        "tencent": "微信视频号",
        "xhs": "小红书创作者",
    }.get(platform, "平台")


def merge_chromium_launch_options(base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """合并 Docker 下常用的 Chromium 启动参数。"""
    out: Dict[str, Any] = dict(base or {})
    args = list(out.get("args") or [])
    for a in CHROMIUM_EXTRA_LAUNCH_ARGS:
        if a not in args:
            args.append(a)
    out["args"] = args
    return out


def is_transient_navigation_error(exc: BaseException) -> bool:
    """是否为可重试的网络/导航类错误（根据 Playwright / Chromium 错误文本判断）。"""
    msg = str(exc).lower()
    needles = (
        "err_connection_closed",
        "err_connection_reset",
        "err_timed_out",
        "err_connection_refused",
        "err_name_not_resolved",
        "err_address_unreachable",
        "err_tunnel_connection_failed",
        "net::err_",
        "navigation timeout",
        "timeout exceeded",
    )
    return any(n in msg for n in needles)


def user_friendly_uploader_error(exc: BaseException, platform_label: str) -> str:
    """面向管理员/前端的简短中文说明；日志仍应记录完整 ``exc``。"""
    if is_transient_navigation_error(exc):
        return (
            f"无法连接{platform_label}页面，请检查网络、防火墙或运行环境是否能访问目标站点后重试。"
        )
    return str(exc)


async def goto_with_retry(
    page: Page,
    url: str,
    *,
    wait_until: str = "domcontentloaded",
    timeout: float = 60000,
    retries: int = 3,
    delay_sec: float = 2.5,
    log_label: str = "goto",
) -> None:
    """对 ``page.goto`` 做有限次重试，仅对网络类错误重试。"""
    last: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            if attempt > 1:
                logger.info("%s succeeded on attempt %s/%s", log_label, attempt, retries)
            return
        except Exception as e:
            last = e
            if not is_transient_navigation_error(e) or attempt >= retries:
                raise
            logger.warning(
                "%s failed (attempt %s/%s): %s — retrying in %.1fs",
                log_label,
                attempt,
                retries,
                e,
                delay_sec,
            )
            await asyncio.sleep(delay_sec)
    if last:
        raise last
