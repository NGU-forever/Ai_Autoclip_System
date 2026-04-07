# -*- coding: utf-8 -*-
"""
浏览器登录管理器 - 复用 Uploader 的交互式浏览器功能

该模块封装了 Uploader 的 interactive_manager，
使其可以在 backend 服务中独立运行。
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Any

# 添加 uploader 路径
UPLOADER_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "AgentOs-Uploader"
if str(UPLOADER_PATH) not in sys.path:
    sys.path.insert(0, str(UPLOADER_PATH))

logger = logging.getLogger(__name__)


class BrowserLoginManager:
    """
    浏览器登录管理器
    
    封装 Uploader 的 InteractiveBrowserManager，
    提供统一的浏览器登录接口。
    """
    
    def __init__(self):
        self._inner_manager = None
        self._initialized = False
    
    async def start(self):
        """启动管理器"""
        if self._initialized:
            return
        
        try:
            # 延迟导入，确保路径已设置
            from src.browser.interactive_manager import get_interactive_browser_manager
            
            self._inner_manager = await get_interactive_browser_manager()
            self._initialized = True
            logger.info("BrowserLoginManager started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start BrowserLoginManager: {e}")
            raise
    
    async def stop(self):
        """停止管理器"""
        if self._inner_manager:
            try:
                await self._inner_manager.stop()
                logger.info("BrowserLoginManager stopped")
            except Exception as e:
                logger.error(f"Error stopping BrowserLoginManager: {e}")
            finally:
                self._inner_manager = None
                self._initialized = False
    
    async def create_session(self, platform: str, existing_account: Optional[dict] = None) -> dict:
        """
        创建浏览器登录会话
        
        Args:
            platform: 平台名称 (douyin, tencent, xhs)
            existing_account: 可选，已有账号信息
            
        Returns:
            会话信息字典
        """
        if not self._initialized or not self._inner_manager:
            raise RuntimeError("BrowserLoginManager not initialized")
        
        return await self._inner_manager.create_session(platform, existing_account)
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """获取会话信息"""
        if not self._initialized or not self._inner_manager:
            return None
        
        return self._inner_manager.get_session(session_id)
    
    async def close_session(self, session_id: str) -> bool:
        """关闭指定会话"""
        if not self._initialized or not self._inner_manager:
            return False
        
        return await self._inner_manager.close_session(session_id)
    
    async def get_account_for_platform(self, platform: str) -> Optional[dict]:
        """获取指定平台的已登录账号"""
        if not self._initialized or not self._inner_manager:
            return None
        
        return await self._inner_manager.get_account_for_platform(platform)
