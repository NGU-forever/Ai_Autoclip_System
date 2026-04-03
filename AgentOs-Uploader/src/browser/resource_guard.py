# -*- coding: utf-8 -*-
"""
RAII 资源守护模块

利用高级异步上下文管理器确保 BrowserContext 与 Page 在任何退出路径下
（正常返回、未捕获异常、asyncio CancelledError、进程信号）都能被 100% 回收。
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from typing import Optional

from playwright.async_api import BrowserContext, Page

from .models import PersistentSession
from .pool import get_browser_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def managed_browser_session(session: PersistentSession):
    """会话级浏览器资源 RAII 守卫

    职责：
    - 从 BrowserPool 创建 Context 与 Page。
    - 自动应用 init_script 与抖音 speed_routes。
    - 在 finally 中通过 asyncio.shield 保证 page.close() / context.close()
      即使遇到 asyncio.CancelledError 也会执行完毕。
    - 清理二维码截图文件。

    Args:
        session: 持久化会话对象（会被写入 session.context / session.page）。

    Yields:
        Page: 已初始化的 Playwright Page 实例。
    """
    from src.utils.base_social_media import set_init_script
    from src.utils.douyin_speed_routes import attach_douyin_speed_routes

    pool = await get_browser_pool()
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None

    try:
        context = await pool.create_context()
        context = await set_init_script(context)
        if session._attach_speed_routes:
            await attach_douyin_speed_routes(context)
        page = await context.new_page()
        session.context = context
        session.page = page
        yield page
    finally:
        # 先从 session 上解绑，防止外部继续使用已失效引用
        session.context = None
        session.page = None

        async def _cleanup():
            if page:
                with suppress(Exception):
                    await page.close()
            if context:
                with suppress(Exception):
                    await context.close()
            if session.qr_code_path and os.path.exists(session.qr_code_path):
                with suppress(Exception):
                    os.remove(session.qr_code_path)

        try:
            await asyncio.shield(_cleanup())
        except asyncio.CancelledError:
            logger.warning(
                f"Browser session cleanup for {session.id} was shielded but caller cancelled"
            )
            raise
