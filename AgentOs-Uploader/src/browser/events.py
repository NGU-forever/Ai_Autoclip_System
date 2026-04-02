# -*- coding: utf-8 -*-
import logging
import asyncio
from typing import Callable, Dict, List, Any

logger = logging.getLogger(__name__)

class StatusEventEmitter:
    """会话状态变更事件发射器"""
    
    def __init__(self):
        self._listeners: List[Callable] = []
    
    def subscribe(self, callback: Callable):
        """订阅状态变更事件"""
        if callback not in self._listeners:
            self._listeners.append(callback)
            
    def unsubscribe(self, callback: Callable):
        """取消订阅"""
        if callback in self._listeners:
            self._listeners.remove(callback)
            
    async def emit(self, session: Any):
        """异步触发事件"""
        for callback in self._listeners:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(session)
                else:
                    callback(session)
            except Exception as e:
                logger.error(f"Error in status change listener: {e}")

# 全局共享实例
status_emitter = StatusEventEmitter()
