# -*- coding: utf-8 -*-
import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

from src.config_manager import config_manager
from uploader.conf import LOCAL_CHROME_PATH
from uploader.utils.playwright_net import merge_chromium_launch_options

logger = logging.getLogger(__name__)

class BrowserPool:
    """浏览器资源池管理器 (单例模式)
    
    职责：
    - 管理全局重量级的 Playwright 和 Browser 实例。
    - 为会话提供轻量级的 BrowserContext 和 Page。
    """
    
    _instance: Optional['BrowserPool'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserPool, cls).__new__(cls)
            cls._instance._playwright = None
            cls._instance._browser = None
            cls._instance._browser_lock = asyncio.Lock()
        return cls._instance
    
    @classmethod
    async def get_instance(cls) -> 'BrowserPool':
        """获取浏览器池单例"""
        return cls()

    async def get_browser(self) -> Browser:
        """确保并获取全局浏览器实例 (线程安全)"""
        async with self._browser_lock:
            if self._browser is not None and self._browser.is_connected():
                return self._browser
            
            # 启动 Playwright 和 Browser
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            
            launch_options = merge_chromium_launch_options({"headless": True})
            if LOCAL_CHROME_PATH:
                launch_options["executable_path"] = LOCAL_CHROME_PATH
            
            self._browser = await self._playwright.chromium.launch(**launch_options)
            logger.info("Global browser instance started (pooling mode)")
            return self._browser

    async def create_context(self, **options) -> BrowserContext:
        """从池中创建一个新的轻量级上下文"""
        browser = await self.get_browser()
        
        default_options = {
            "viewport": {"width": 1280, "height": 800},
            "locale": "zh-CN",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        }
        # 合并选项
        default_options.update(options)
        
        context = await browser.new_context(**default_options)
        return context

    async def shutdown(self):
        """完全关闭浏览器池及所有资源"""
        async with self._browser_lock:
            if self._browser and self._browser.is_connected():
                try:
                    await self._browser.close()
                    logger.info("Global browser instance closed")
                except Exception as e:
                    logger.debug(f"Error closing global browser: {e}")
                self._browser = None
            
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.debug(f"Error stopping playwright: {e}")
                self._playwright = None

# 辅助方法
async def get_browser_pool() -> BrowserPool:
    return await BrowserPool.get_instance()
