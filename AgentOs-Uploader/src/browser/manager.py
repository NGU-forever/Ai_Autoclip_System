# -*- coding: utf-8 -*-
import asyncio
import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from src.config_manager import config_manager
from uploader.conf import settings

from .models import PersistentSession, SessionStatus
from .pool import get_browser_pool
from .flows.qr_login import QRLoginFlow
from .events import status_emitter

logger = logging.getLogger(__name__)

class SessionManager:
    """会话管理器 (单例模式)
    
    职责：
    - 维护活跃会话注册表 `sessions`。
    - 处理会话心跳更新与后台自动清理逻辑。
    - 统筹会话的创建与资源释放。
    """
    
    _instance: Optional['SessionManager'] = None
    _lock = asyncio.Lock()
    
    HEARTBEAT_TIMEOUT = config_manager.get("browser_heartbeat_timeout")
    HEARTBEAT_CHECK_INTERVAL = config_manager.get("browser_heartbeat_check_interval")
    QR_WAIT_TIMEOUT = config_manager.get("browser_qr_wait_timeout")
    REFRESH_QR_WAIT_TIMEOUT = config_manager.get("browser_refresh_qr_wait_timeout")
    MAX_CONCURRENT_SESSIONS = config_manager.get("browser_max_concurrent_sessions")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SessionManager, cls).__new__(cls)
            cls._instance.sessions: Dict[str, PersistentSession] = {}
            cls._instance._cleanup_task: Optional[asyncio.Task] = None
        return cls._instance

    @classmethod
    async def get_instance(cls) -> 'SessionManager':
        """获取会话管理器单例"""
        return cls()

    async def start(self):
        """启动管理器心跳清理循环"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("SessionManager started")

    async def stop(self):
        """停止管理器并清理所有活跃会话"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try: await self._cleanup_task
            except asyncio.CancelledError: pass
        
        # 关闭所有活跃会话
        for session_id in list(self.sessions.keys()):
            await self.close_session(session_id)
        
        logger.info("SessionManager stopped")

    async def create_session(self, platform: str) -> PersistentSession:
        """创建新的持久化会话"""
        async with self._lock:
            # 1. 如果已有同平台活跃会话，先关闭
            existing = [s for s in self.sessions.values() if s.platform == platform and s.status not in (SessionStatus.SUCCESS, SessionStatus.FAILED)]
            for s in existing:
                await self._close_session_internal(s.id)
            
            # 2. 检查并发上限
            if len(self.sessions) >= self.MAX_CONCURRENT_SESSIONS:
                raise RuntimeError(f"Too many concurrent sessions (max: {self.MAX_CONCURRENT_SESSIONS})")
            
            session_id = str(uuid.uuid4())
            qr_dir = self._ensure_qr_dir()
            
            session = PersistentSession(
                id=session_id,
                platform=platform,
                status=SessionStatus.INITIALIZING,
                qr_code_path=str(qr_dir / f"persistent_{session_id}.png")
            )
            self.sessions[session_id] = session
            
            # 启动初始化流程 (异步)
            self._track_task(session, QRLoginFlow.start_init_platform(session))
            
            logger.info(f"Created session {session_id} for platform {platform}")
            return session

    async def close_session(self, session_id: str):
        """外部接口：关闭指定会话"""
        async with self._lock:
            await self._close_session_internal(session_id)

    async def _close_session_internal(self, session_id: str):
        """核心释放逻辑：停止任务、清理资源"""
        session = self.sessions.pop(session_id, None)
        if not session: return
        
        logger.info(f"Closing persistent session {session_id}")
        
        # 1. 取消所有后台任务
        for task in list(session._background_tasks):
            if not task.done():
                task.cancel()
        
        # 2. 回收浏览器资源
        try:
            if session.page: await session.page.close()
            if session.context: await session.context.close()
        except Exception as e:
            logger.debug(f"Error closing browser resources: {e}")
        
        # 3. 清理截图文件
        if session.qr_code_path and os.path.exists(session.qr_code_path):
            try: os.remove(session.qr_code_path)
            except: pass

    def update_heartbeat(self, session_id: str) -> bool:
        """更新会话心跳状态"""
        session = self.sessions.get(session_id)
        if not session: return False
        
        # 健康检查：如 page 已关闭则标记恢复
        if session.page and session.page.is_closed():
            session._needs_recovery = True
            
        session.last_heartbeat = time.time()
        return True

    def get_session(self, session_id: str) -> Optional[PersistentSession]:
        """获取指定会话"""
        return self.sessions.get(session_id)

    async def get_qr_code_data(self, session_id: str) -> Optional[bytes]:
        """获取二维码图片数据，支持等待就绪"""
        session = self.sessions.get(session_id)
        if not session: return None
        
        try:
            await asyncio.wait_for(session.qr_ready.wait(), timeout=self.QR_WAIT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"QR ready timeout for session {session_id}")
            return None
        
        if session.qr_code_path and os.path.exists(session.qr_code_path):
            try:
                with open(session.qr_code_path, "rb") as f:
                    return f.read()
            except OSError: pass
        return None

    async def recover_session(self, session_id: str) -> bool:
        """尝试恢复崩溃的会话"""
        session = self.sessions.get(session_id)
        if not session or not session._needs_recovery: return False
        if session.status in [SessionStatus.SUCCESS, SessionStatus.FAILED]: return False
        
        logger.info(f"Attempting to recover session {session_id} ({session.platform})")
        try:
            # 1. 清理旧资源
            if session.page: await session.page.close()
            if session.context: await session.context.close()
            
            # 2. 重新启动初始化流
            session.status = SessionStatus.INITIALIZING
            session.error_msg = None
            session.qr_ready.clear()
            session._needs_recovery = False
            
            self._track_task(session, QRLoginFlow.start_init_platform(session))
            return True
        except Exception as e:
            logger.error(f"Failed to recover session {session_id}: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = f"会话恢复失败: {str(e)[:100]}"
            session.qr_ready.set()
            return False

    async def refresh_session_qr_wait(self, session_id: str) -> Tuple[bool, Optional[str]]:
        """执行刷新并等待新二维码就绪"""
        session = self.sessions.get(session_id)
        if not session: return False, "会话不存在"
        
        # 重新触发初始化逻辑（重载页面）
        session.qr_ready.clear()
        self._track_task(session, QRLoginFlow.start_init_platform(session))
        
        try:
            await asyncio.wait_for(session.qr_ready.wait(), timeout=self.REFRESH_QR_WAIT_TIMEOUT)
            if session.status == SessionStatus.FAILED:
                return False, session.error_msg or "刷新二维码失败"
            return True, None
        except asyncio.TimeoutError:
            return False, "二维码生成超时"

    async def close_all_sessions(self):
        """关闭所有持久化会话"""
        for sid in list(self.sessions.keys()):
            await self.close_session(sid)

    async def refresh_all_sessions(self) -> dict:
        """批量刷新所有可刷新的会话"""
        refreshed = 0
        skipped = 0
        errors = []
        for sid, session in list(self.sessions.items()):
            if session.status in [SessionStatus.SUCCESS, SessionStatus.INITIALIZING]:
                skipped += 1
                continue
            ok, err = await self.refresh_session_qr_wait(sid)
            if ok: refreshed += 1
            else: errors.append(f"{session.platform}:{sid[:8]} - {err}")
        return {"refreshed": refreshed, "skipped": skipped, "errors": errors}

    async def _cleanup_loop(self):
        """定期执行过期清理任务"""
        while True:
            try:
                await asyncio.sleep(self.HEARTBEAT_CHECK_INTERVAL)
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError: break
            except Exception as e: logger.error(f"Cleanup loop error: {e}")

    async def _cleanup_expired_sessions(self):
        """清理超时会话并尝试恢复标记为异常的会话"""
        now = time.time()
        expired = []
        recovery = []
        
        for sid, s in list(self.sessions.items()):
            if now - s.last_heartbeat > self.HEARTBEAT_TIMEOUT:
                expired.append(sid)
            elif s._needs_recovery and s.status not in [SessionStatus.SUCCESS, SessionStatus.FAILED]:
                recovery.append(sid)
        
        for sid in expired:
            await self.close_session(sid)
        for sid in recovery:
            await self.recover_session(sid)

    def _ensure_qr_dir(self) -> Path:
        os.makedirs(settings.uploader_cookies_path, exist_ok=True)
        qr_dir = Path(settings.storage_root) / "uploader" / "qr_codes"
        os.makedirs(qr_dir, exist_ok=True)
        return qr_dir

    def _track_task(self, session: PersistentSession, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        session._background_tasks.add(task)
        task.add_done_callback(session._background_tasks.discard)
        return task

# 快捷获取实例的方法
async def get_session_manager() -> SessionManager:
    return await SessionManager.get_instance()
