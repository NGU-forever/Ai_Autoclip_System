# -*- coding: utf-8 -*-
import logging
from typing import Optional

from .models import PersistentSession, SessionStatus
from .pool import get_browser_pool, BrowserPool
from .manager import get_session_manager, SessionManager
from .events import status_emitter

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

# --- 事件解耦注册 ---
# 负责将内部状态变更事件映射到现有的 WebSocket 通知逻辑
async def _on_session_status_changed(session: PersistentSession):
    try:
        from src.upload.websocket import notify_session_status
        await notify_session_status(
            session_id=session.id,
            platform=session.platform,
            status=session.status.value,
            user_name=session.user_name,
            error=session.error_msg,
        )
    except Exception as e:
        logger.debug(f"Failed to notify status change via WebSocket: {e}")

# 注册默认监听者
status_emitter.subscribe(_on_session_status_changed)

__all__ = [
    "get_persistent_browser_manager",
    "get_session_manager",
    "get_browser_pool",
    "shutdown_browser_service",
    "PersistentSession",
    "SessionStatus",
]
