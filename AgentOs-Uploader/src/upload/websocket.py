# -*- coding: utf-8 -*-
"""
WebSocket 管理器 for QR 登录实时推送
"""

import logging
from typing import Dict, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class QRLoginWebSocketManager:
    """QR 登录 WebSocket 连接管理器
    
    管理所有活跃的 WebSocket 连接，负责状态变更时的实时推送。
    """
    
    def __init__(self):
        # session_id -> WebSocket 映射
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, session_id: str, websocket: WebSocket) -> bool:
        """建立 WebSocket 连接
        
        Args:
            session_id: 会话 ID
            websocket: WebSocket 对象
            
        Returns:
            是否成功接受连接
        """
        try:
            await websocket.accept()
            self.active_connections[session_id] = websocket
            logger.info(f"WebSocket connected for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to accept WebSocket for {session_id}: {e}")
            return False
    
    async def disconnect(self, session_id: str) -> None:
        """断开 WebSocket 连接"""
        if session_id in self.active_connections:
            try:
                ws = self.active_connections[session_id]
                await ws.close()
            except Exception:
                pass
            finally:
                del self.active_connections[session_id]
                logger.info(f"WebSocket disconnected for session {session_id}")
    
    async def send_status_update(self, session_id: str, status_data: dict) -> bool:
        """发送状态更新到客户端
        
        Args:
            session_id: 会话 ID
            status_data: 状态数据字典
            
        Returns:
            是否成功发送
        """
        ws = self.active_connections.get(session_id)
        if not ws:
            return False
        
        try:
            await ws.send_json(status_data)
            logger.debug(f"Status update sent to {session_id}: {status_data.get('status')}")
            return True
        except Exception as e:
            logger.warning(f"Failed to send status to {session_id}: {e}")
            # 发送失败，清理连接
            await self.disconnect(session_id)
            return False
    
    async def send_to_all(self, status_data: dict) -> None:
        """广播状态更新到所有连接"""
        disconnected = []
        for session_id, ws in list(self.active_connections.items()):
            try:
                await ws.send_json(status_data)
            except Exception as e:
                logger.warning(f"Failed to broadcast to {session_id}: {e}")
                disconnected.append(session_id)
        
        # 清理断开的连接
        for session_id in disconnected:
            self.active_connections.pop(session_id, None)
    
    def is_connected(self, session_id: str) -> bool:
        """检查指定会话是否有活跃的 WebSocket 连接"""
        return session_id in self.active_connections
    
    def get_connection_count(self) -> int:
        """获取当前活跃连接数"""
        return len(self.active_connections)


# 全局 WebSocket 管理器实例
ws_manager = QRLoginWebSocketManager()


async def notify_session_status(
    session_id: str,
    platform: str,
    status: str,
    user_name: Optional[str] = None,
    error: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None
) -> bool:
    """通知会话状态变更
    
    便捷函数，用于从 persistent_browser_service 调用
    
    Args:
        session_id: 会话 ID
        platform: 平台名称
        status: 状态值
        user_name: 用户名（登录成功时）
        error: 错误信息（失败时）
        extra_data: 额外数据
        
    Returns:
        是否成功通知
    """
    data = {
        "sessionId": session_id,
        "platform": platform,
        "status": status,
        "timestamp": import_time(),
    }
    
    if user_name:
        data["userName"] = user_name
    if error:
        data["error"] = error
    if extra_data:
        data.update(extra_data)
    
    return await ws_manager.send_status_update(session_id, data)


def import_time() -> float:
    """获取当前时间戳"""
    import time
    return time.time()
