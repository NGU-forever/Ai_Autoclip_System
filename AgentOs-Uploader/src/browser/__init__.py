# -*- coding: utf-8 -*-
import logging
from typing import Optional

from .models import PersistentSession, SessionStatus
from .pool import get_browser_pool, BrowserPool
from .manager import get_session_manager, SessionManager

logger = logging.getLogger(__name__)

# --- 公共接口声明 ---
async def get_persistent_browser_manager() -> SessionManager:
    """对齐旧版 API 的快捷获取方式"""
    manager = await get_session_manager()
    await manager.start()
    return manager

async def shutdown_browser_service():
    """彻底关闭所有浏览器相关服务资源"""
    manager = await get_session_manager()
    await manager.stop()
    
    pool = await get_browser_pool()
    await pool.shutdown()

__all__ = [
    "get_persistent_browser_manager",
    "get_session_manager",
    "get_browser_pool",
    "shutdown_browser_service",
    "PersistentSession",
    "SessionStatus",
]
