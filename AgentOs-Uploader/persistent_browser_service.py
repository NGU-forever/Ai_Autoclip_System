# -*- coding: utf-8 -*-
"""
持久化浏览器会话服务
用于后台常驻浏览器实例，支持二维码刷新而无需重启浏览器

优化特性：
1. 浏览器实例池化：全局共享 Browser，每个会话使用轻量级 Context
2. 增强异常恢复：心跳检查中包含浏览器健康检测，支持自动恢复
3. 统一配置参数：所有超时参数从 settings 读取，支持环境变量覆盖
"""

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from playwright.async_api import async_playwright, Browser, BrowserContext, Frame, Page, Playwright

from src.config import settings
from uploader.conf import LOCAL_CHROME_PATH
from src.qr_login.drivers import get_driver
from src.qr_login.success_detector import LoginSuccessDetector
from uploader.qr_login_service import get_qr_login_service
from uploader.utils.base_social_media import set_init_script
from uploader.utils.douyin_speed_routes import attach_douyin_speed_routes
from uploader.utils.playwright_net import (
    goto_with_retry,
    merge_chromium_launch_options,
    platform_label_for_error,
    user_friendly_uploader_error,
)

import logging

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    INITIALIZING = "initializing"  # 正在初始化浏览器
    READY = "ready"                # 浏览器就绪，二维码已生成
    SCANNING = "scanning"          # 已扫码，等待确认
    SUCCESS = "success"            # 登录成功
    FAILED = "failed"              # 登录失败
    EXPIRED = "expired"            # 二维码过期


@dataclass
class PersistentSession:
    """持久化浏览器会话"""
    id: str
    platform: str  # douyin, tencent, xhs
    status: SessionStatus
    # Note: browser 实例现在由 PersistentBrowserManager 全局管理，会话只保存 context 和 page
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None
    qr_code_path: Optional[str] = None
    cookie_file: Optional[str] = None
    user_name: Optional[str] = None
    error_msg: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: float = field(default_factory=time.time)
    qr_ready: asyncio.Event = field(default_factory=asyncio.Event)
    _login_success_event: asyncio.Event = field(default_factory=asyncio.Event)
    # Phase 2+4: 显式跟踪所有后台任务，关闭时统一取消
    _background_tasks: set = field(default_factory=set)
    # 会话恢复标记：浏览器崩溃后需要恢复
    _needs_recovery: bool = False
    # 保存会话的初始 URL 用于恢复
    _init_url: Optional[str] = None
    # 是否附加了抖音加速路由
    _attach_speed_routes: bool = False


class PersistentBrowserManager:
    """持久化浏览器管理器
    
    采用浏览器实例池化设计：
    - 全局共享一个 Browser 实例（重量级）
    - 每个会话创建独立的 BrowserContext（轻量级，类似无痕窗口）
    - 大幅降低资源占用，提升启动速度
    """
    
    # 从 settings 读取配置，支持环境变量覆盖
    HEARTBEAT_TIMEOUT = settings.browser_heartbeat_timeout
    HEARTBEAT_CHECK_INTERVAL = settings.browser_heartbeat_check_interval
    QR_CODE_VALIDITY = settings.browser_qr_validity
    QR_WAIT_TIMEOUT = settings.browser_qr_wait_timeout
    REFRESH_QR_WAIT_TIMEOUT = settings.browser_refresh_qr_wait_timeout
    LOGIN_POLL_MAX_TIME = settings.browser_login_poll_max_time
    MAX_CONCURRENT_SESSIONS = settings.browser_max_concurrent_sessions
    
    def __init__(self):
        self.sessions: Dict[str, PersistentSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # 全局浏览器实例（池化核心）
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._browser_lock = asyncio.Lock()
        self._browser_started = False
    
    async def start(self):
        """启动管理器，初始化全局浏览器实例，开始心跳检查任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        # 启动全局浏览器实例
        await self._ensure_browser()
        logger.info("PersistentBrowserManager started")
    
    async def stop(self):
        """停止管理器，关闭所有会话和全局浏览器实例"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有会话
        for session in list(self.sessions.values()):
            await self.close_session(session.id)
        
        # 关闭全局浏览器实例
        await self._stop_global_browser()
        
        logger.info("PersistentBrowserManager stopped")
    
    async def _ensure_browser(self) -> Browser:
        """确保全局浏览器实例已启动（线程安全）
        
        这是浏览器池化的核心方法：所有会话共享同一个 Browser 实例，
        每个会话只创建轻量级的 BrowserContext。
        """
        async with self._browser_lock:
            if self._browser is not None and not self._browser.is_closed():
                return self._browser
            
            # 启动新的浏览器实例
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            
            launch_options = merge_chromium_launch_options({"headless": True})
            if LOCAL_CHROME_PATH:
                launch_options["executable_path"] = LOCAL_CHROME_PATH
            
            self._browser = await self._playwright.chromium.launch(**launch_options)
            self._browser_started = True
            logger.info("Global browser instance started (pooling mode)")
            return self._browser
    
    async def _stop_global_browser(self):
        """关闭全局浏览器实例"""
        async with self._browser_lock:
            if self._browser and not self._browser.is_closed():
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
            
            self._browser_started = False
    
    async def _cleanup_loop(self):
        """定期清理超时会话的后台任务"""
        while True:
            try:
                await asyncio.sleep(self.HEARTBEAT_CHECK_INTERVAL)
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_expired_sessions(self):
        """清理心跳超时的会话，并处理需要恢复的会话"""
        now = time.time()
        expired_sessions = []
        recovery_sessions = []
        
        for session_id, session in self.sessions.items():
            # 检查心跳超时
            if now - session.last_heartbeat > self.HEARTBEAT_TIMEOUT:
                expired_sessions.append(session_id)
            # 检查是否需要恢复
            elif session._needs_recovery and session.status not in [
                SessionStatus.SUCCESS, SessionStatus.FAILED
            ]:
                recovery_sessions.append(session_id)
        
        # 关闭超时会话
        for session_id in expired_sessions:
            logger.info(f"Session {session_id} heartbeat timeout, closing")
            await self.close_session(session_id)
        
        # 尝试恢复崩溃的会话
        for session_id in recovery_sessions:
            logger.info(f"Session {session_id} needs recovery, attempting auto-recovery")
            recovered = await self.recover_session(session_id)
            if not recovered:
                logger.warning(f"Failed to recover session {session_id}, marking as failed")
                session = self.sessions.get(session_id)
                if session:
                    session.status = SessionStatus.FAILED
                    session.error_msg = "浏览器进程异常，恢复失败"
    
    def _ensure_dirs(self):
        """确保目录存在"""
        os.makedirs(settings.uploader_cookies_path, exist_ok=True)
        qr_dir = Path(settings.storage_root) / "uploader" / "qr_codes"
        os.makedirs(qr_dir, exist_ok=True)
        return qr_dir
    
    def _track_task(self, session: PersistentSession, coro) -> asyncio.Task:
        """创建并追踪一个后台任务，任务完成后自动从集合移除。"""
        task = asyncio.create_task(coro)
        session._background_tasks.add(task)
        task.add_done_callback(session._background_tasks.discard)
        return task

    async def create_session(self, platform: str) -> PersistentSession:
        """创建新的持久化会话"""
        async with self._lock:
            # 检查是否已有同平台的活跃会话，如果有则关闭
            existing = [
                s for s in self.sessions.values() 
                if s.platform == platform and s.status not in [SessionStatus.SUCCESS, SessionStatus.FAILED]
            ]
            for s in existing:
                logger.info(f"Closing existing session {s.id} for platform {platform}")
                await self._close_session_internal(s.id)
            
            # 检查并发会话数限制
            if len(self.sessions) >= self.MAX_CONCURRENT_SESSIONS:
                raise RuntimeError(f"Too many concurrent sessions (max: {self.MAX_CONCURRENT_SESSIONS})")
            
            session_id = str(uuid.uuid4())
            qr_dir = self._ensure_dirs()
            
            session = PersistentSession(
                id=session_id,
                platform=platform,
                status=SessionStatus.INITIALIZING,
                qr_code_path=str(qr_dir / f"persistent_{session_id}.png")
            )
            self.sessions[session_id] = session
            
            # 启动异步任务初始化浏览器，并显式跟踪
            self._track_task(session, self._init_browser(session))
            
            logger.info(f"Created persistent session {session_id} for platform {platform}")
            return session
    
    async def _init_browser(self, session: PersistentSession):
        """初始化浏览器实例"""
        try:
            if session.platform == "douyin":
                await self._init_douyin(session)
            elif session.platform == "tencent":
                await self._init_tencent(session)
            elif session.platform == "xhs":
                await self._init_xhs(session)
            else:
                session.status = SessionStatus.FAILED
                session.error_msg = f"不支持的平台: {session.platform}"
                session.qr_ready.set()
        except Exception as e:
            logger.error(f"Error initializing browser for session {session.id}: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = user_friendly_uploader_error(
                e, platform_label_for_error(session.platform)
            )
            await self._dispose_session_browser_resources(session)
            session.qr_ready.set()

    async def _dispose_session_browser_resources(self, session: PersistentSession) -> None:
        """关闭会话内 Playwright 资源，不从 sessions 中移除（用于 FAILED 等状态释放进程内资源）
        
        注意：使用浏览器池化后，Browser 实例是全局共享的，这里只关闭 Context 和 Page。
        """
        # 关闭 page
        try:
            if session.page:
                await session.page.close()
        except Exception as e:
            logger.debug("dispose: page close: %s", e)
        session.page = None
        
        # 关闭 context
        try:
            if session.context:
                await session.context.close()
        except Exception as e:
            logger.debug("dispose: context close: %s", e)
        session.context = None
        
        # 注意：不再关闭 browser 和 playwright，因为它们是全局共享的
        # session.browser 和 session._playwright 字段已不再使用（已从 dataclass 移除）
    
    async def _dispose_session_context_only(self, session: PersistentSession) -> None:
        """仅关闭会话的 Context 和 Page，用于会话恢复场景"""
        await self._dispose_session_browser_resources(session)
    
    # ─────────────────────────────────────────────────────────────────
    # Phase 2: 共享浏览器初始化基础方法
    # ─────────────────────────────────────────────────────────────────
    async def _init_browser_context(
        self,
        session: PersistentSession,
        url: str,
        log_label: str,
        *,
        attach_speed_routes: bool = False,
    ) -> Page:
        """
        共享浏览器初始化逻辑：使用全局 Browser -> 创建 Context -> Page -> goto。
        各平台只需传入目标 URL，平台特有逻辑（捕获二维码）在调用方实现。
        返回已加载就绪的 Page 对象。
        
        注意：这是浏览器池化的核心，所有会话共享同一个 Browser 实例，
        每个会话只创建轻量级的 BrowserContext（类似无痕窗口）。
        """
        # 确保全局浏览器实例已启动
        browser = await self._ensure_browser()
        
        # 保存配置用于可能的恢复
        session._init_url = url
        session._attach_speed_routes = attach_speed_routes

        # 创建轻量级 Context（比启动新 Browser 快 3-5 倍，资源占用低）
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        context = await set_init_script(context)
        if attach_speed_routes:
            await attach_douyin_speed_routes(context)
        session.context = context

        page = await context.new_page()
        session.page = page

        await goto_with_retry(
            page,
            url,
            wait_until="domcontentloaded",
            timeout=60000,
            retries=3,
            delay_sec=2.5,
            log_label=log_label,
        )
        return page

    # ─────────────────────────────────────────────────────────────────
    # Driver & Manager 架构：平台初始化（Phase 4 重构）
    # ─────────────────────────────────────────────────────────────────
    
    # 平台 URL 配置
    PLATFORM_URLS = {
        "douyin": "https://creator.douyin.com/",
        "tencent": "https://channels.weixin.qq.com/login.html",
        "xhs": "https://creator.xiaohongshu.com/",
    }
    
    async def _init_platform(self, session: PersistentSession):
        """统一的平台初始化方法（使用 Driver 架构）
        
        Manager 职责：
        1. 管理浏览器生命周期（browser/context/page）
        2. 调用 Driver 执行平台特定的 DOM 操作
        3. 统一成功判定
        """
        platform = session.platform
        logger.info(f"Initializing {platform} browser for session {session.id}")
        
        try:
            # 1. 初始化浏览器上下文（Manager 职责）
            url = self.PLATFORM_URLS.get(platform)
            if not url:
                raise ValueError(f"Unknown platform: {platform}")
            
            page = await self._init_browser_context(
                session,
                url,
                log_label=f"{platform} session {session.id} goto",
                attach_speed_routes=(platform == "douyin"),
            )
            
            # 2. 获取 Driver（纯 DOM 操作层）
            driver = get_driver(platform)
            
            # 3. 准备登录页面（Driver 职责）
            await driver.prepare_login_page(page)
            
            # 4. 捕获二维码（Driver 职责）
            ok = await driver.capture_qr_code(page, session.qr_code_path)
            png_ok = (
                ok
                and os.path.exists(session.qr_code_path)
                and os.path.getsize(session.qr_code_path) >= 200
            )
            
            if not png_ok:
                session.status = SessionStatus.FAILED
                session.error_msg = "二维码生成失败"
                session.qr_ready.set()
                await self._notify_status_change(session)
                return
            
            # 5. 二维码就绪
            session.status = SessionStatus.READY
            session.qr_ready.set()
            logger.info(f"{platform} QR code captured for session {session.id}")
            await self._notify_status_change(session)
            
            # 6. 附加登录监听器和启动轮询
            self._attach_login_monitors(session)
            self._track_task(session, self._poll_login_status_with_driver(session, driver))
            
        except Exception as e:
            logger.error(f"Error during {platform} initialization: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = user_friendly_uploader_error(
                e, platform_label_for_error(platform)
            )
            await self._dispose_session_browser_resources(session)
            session.qr_ready.set()
    
    # 保留旧的初始化方法作为兼容层，内部调用新的统一方法
    async def _init_douyin(self, session: PersistentSession):
        """初始化抖音浏览器（兼容层，使用 Driver 架构）"""
        await self._init_platform(session)
    
    async def _init_tencent(self, session: PersistentSession):
        """初始化视频号浏览器（兼容层，使用 Driver 架构）"""
        await self._init_platform(session)
    
    async def _init_xhs(self, session: PersistentSession):
        """初始化小红书浏览器（兼容层，使用 Driver 架构）"""
        await self._init_platform(session)
    
    async def _poll_login_status_with_driver(self, session: PersistentSession, driver) -> None:
        """使用 Driver 的状态轮询（统一成功判定）
        
        职责分离：
        - Driver: 快速检测扫码状态变化（scanning/expired）
        - Manager: 统一成功判定（使用 LoginSuccessDetector）
        """
        try:
            platform_timeout = settings.get_platform_qr_validity(session.platform)
            auto_refresh_interval = 10
            last_auto_refresh_check = 0
            
            for i in range(platform_timeout):
                # 检查会话是否还存在
                if session.id not in self.sessions:
                    logger.info(f"Session {session.id} no longer exists, stopping poll")
                    return
                
                # 检查是否需要恢复（浏览器崩溃）
                if session._needs_recovery:
                    logger.info(f"Session {session.id} marked for recovery, stopping poll")
                    return
                
                # 检查是否已登录成功
                if session.status == SessionStatus.SUCCESS:
                    await self._notify_status_change(session)
                    return
                
                page = session.page
                if not page:
                    logger.warning(f"Page not available for session {session.id}")
                    return
                
                # ─────────────────────────────────────────────────────────
                # Driver 层：快速检测扫码状态
                # ─────────────────────────────────────────────────────────
                scan_status = await driver.detect_scan_status(page)
                
                if scan_status == 'scanning' and session.status != SessionStatus.SCANNING:
                    session.status = SessionStatus.SCANNING
                    logger.info(f"[{session.platform}] QR code scanned, waiting for confirmation")
                    await self._notify_status_change(session)
                
                elif scan_status == 'expired' and session.status == SessionStatus.READY:
                    logger.info(f"[{session.platform}] QR expired detected by Driver")
                    # 触发自动刷新
                    if await driver.refresh_qr_code(page):
                        logger.info(f"[{session.platform}] QR auto-refreshed by Driver")
                        last_auto_refresh_check = 0
                        continue
                    else:
                        session.status = SessionStatus.EXPIRED
                        session.error_msg = "二维码已过期"
                        await self._notify_status_change(session)
                        return
                
                # ─────────────────────────────────────────────────────────
                # Manager 层：统一成功判定（使用 LoginSuccessDetector）
                # ─────────────────────────────────────────────────────────
                if await LoginSuccessDetector.check(page, session.platform):
                    # 登录成功，获取用户名
                    session.user_name = await driver.get_user_name(page)
                    await self._handle_login_success(session)
                    await self._notify_status_change(session)
                    return
                
                # Driver 辅助：自动刷新检测（每10秒一次）
                if session.status == SessionStatus.READY and i >= last_auto_refresh_check + auto_refresh_interval:
                    last_auto_refresh_check = i
                    is_expired = await self._detect_qr_expired(session)
                    if is_expired:
                        logger.info(f"[{session.platform}] QR expired detected at {i}s, auto-refreshing")
                        await self._notify_status_change(session)
                        if await driver.refresh_qr_code(page):
                            logger.info(f"[{session.platform}] QR auto-refreshed successfully")
                            last_auto_refresh_check = 0
                            continue
                        else:
                            session.status = SessionStatus.EXPIRED
                            session.error_msg = "二维码已过期，自动刷新失败"
                            await self._notify_status_change(session)
                            return
                
                # 每10秒记录一次日志
                if i > 0 and i % 10 == 0:
                    current_url = page.url
                    logger.debug(f"[{session.platform}] Polling login status: {i}s/{platform_timeout}s, url={current_url}")
                
                await asyncio.sleep(1)
            
            # 超时
            logger.warning(f"Login timeout for session {session.id} ({session.platform})")
            session.status = SessionStatus.EXPIRED
            session.error_msg = "登录超时，请刷新二维码重试"
            await self._notify_status_change(session)
            
        except Exception as e:
            logger.error(f"Error polling login status for session {session.id}: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = f"检测登录状态出错: {str(e)[:100]}"
            await self._notify_status_change(session)

    @staticmethod
    def _url_hard_logged_in(platform: str, url: str) -> bool:
        """
        与历史轮询逻辑一致：明确的成功 URL，避免仅靠模糊打分漏检。
        视频号登录后常见为 login.html#/platform/...，不能要求路径里出现连续的 .com/platform。
        """
        u = url.lower()
        if platform == "douyin":
            return "creator-micro/content/upload" in u
        if platform == "tencent":
            if "channels.weixin.qq.com" not in u:
                return False
            if "#/platform" in u or "#/creator" in u:
                return True
            return "platform/post/create" in u or "platform/post/list" in u
        if platform == "xhs":
            return "creator-micro/content/upload" in u
        return False

    def _schedule_login_probe(self, session: PersistentSession, reason: str) -> None:
        """路由 / 加载变化后短防抖再检测，避免 SPA 跳转中途误判。"""
        if session.status not in (
            SessionStatus.READY,
            SessionStatus.SCANNING,
            SessionStatus.EXPIRED,
        ):
            return
        old = getattr(session, "_login_probe_task", None)
        if old and not old.done():
            old.cancel()

        async def _probe() -> None:
            try:
                await asyncio.sleep(0.45)
                if session.id not in self.sessions:
                    return
                if session.status == SessionStatus.SUCCESS:
                    return
                if await self._check_login_success_indicators(session):
                    await self._handle_login_success(session)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug("login probe (%s): %s", reason, e)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("login probe skipped (%s): no event loop", reason)
            return
        setattr(session, "_login_probe_task", loop.create_task(_probe()))

    def _attach_login_monitors(self, session: PersistentSession) -> None:
        """主页面导航与 load 事件触发登录检测（配合轮询）。"""
        page = session.page
        if not page or getattr(session, "_login_monitors_attached", False):
            return
        setattr(session, "_login_monitors_attached", True)

        def on_framenavigated(frame: Frame) -> None:
            if session.status in (
                SessionStatus.SUCCESS,
                SessionStatus.FAILED,
                SessionStatus.INITIALIZING,
            ):
                return
            try:
                if frame != page.main_frame:
                    return
            except Exception:
                return
            self._schedule_login_probe(session, "framenavigated")

        def on_load(*_args: object) -> None:
            if session.status in (
                SessionStatus.SUCCESS,
                SessionStatus.FAILED,
                SessionStatus.INITIALIZING,
            ):
                return
            self._schedule_login_probe(session, "load")

        page.on("framenavigated", on_framenavigated)
        page.on("load", on_load)
        logger.info("Attached login monitors for session %s (%s)", session.id, session.platform)
    
    # ===== 登录成功检测配置 =====
    # URL 模式：匹配登录成功后的页面路径


    async def _check_login_success_indicators(self, session: PersistentSession) -> bool:
        """
        综合检测登录成功标志
        使用统一的 LoginSuccessDetector 提高准确性
        """
        if not session.page:
            return False
        
        return await LoginSuccessDetector.check(session.page, session.platform)

    async def _detect_qr_expired(self, session: PersistentSession) -> bool:
        """检测页面是否显示二维码已过期
        
        通过两种方式检测：
        1. 页面文本关键词匹配
        2. 平台特定的 CSS 选择器匹配
        
        Returns:
            True 表示检测到二维码已过期
        """
        if not session.page:
            return False
        
        try:
            page = session.page
            
            # 方式1：文本关键词检测
            page_text = await page.content()
            expired_keywords = settings.qr_expired_keywords
            text_match = any(keyword in page_text for keyword in expired_keywords)
            
            if text_match:
                logger.debug(f"[{session.platform}] QR expired detected by keywords")
                return True
            
            # 方式2：CSS 选择器检测（更精确）
            selectors = settings.qr_expired_selectors.get(session.platform, [])
            for selector in selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            logger.debug(f"[{session.platform}] QR expired detected by selector: {selector}")
                            return True
                except Exception:
                    continue
            
            return False
        except Exception as e:
            logger.debug(f"Error detecting QR expired: {e}")
            return False
    
    async def _notify_status_change(self, session: PersistentSession) -> None:
        """通知所有监听者会话状态变更
        
        通过 WebSocket 推送状态更新到前端
        """
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
            # WebSocket 通知失败不应影响主流程
            logger.debug(f"Failed to notify status change: {e}")
    
    async def _poll_login_status(self, session: PersistentSession):
        """轮询检查登录状态（增强版，支持自动刷新和 WebSocket 通知）"""
        try:
            # 使用平台特定的超时时间
            platform_timeout = settings.get_platform_qr_validity(session.platform)
            auto_refresh_interval = 10  # 每10秒检测一次是否需要自动刷新
            last_auto_refresh_check = 0
            
            for i in range(platform_timeout):
                # 检查会话是否还存在
                if session.id not in self.sessions:
                    logger.info(f"Session {session.id} no longer exists, stopping poll")
                    return
                
                # 检查是否需要恢复（浏览器崩溃）
                if session._needs_recovery:
                    logger.info(f"Session {session.id} marked for recovery, stopping poll")
                    return
                
                # 检查是否已登录成功
                if session.status == SessionStatus.SUCCESS:
                    await self._notify_status_change(session)
                    return
                
                page = session.page
                if not page:
                    logger.warning(f"Page not available for session {session.id}")
                    return
                
                # 使用增强的检测方法
                is_logged_in = await self._check_login_success_indicators(session)
                if is_logged_in:
                    await self._handle_login_success(session)
                    await self._notify_status_change(session)
                    return
                
                # 检查是否已扫码（等待确认）
                if session.status == SessionStatus.READY:
                    try:
                        # 检测"已扫码"或"扫描成功"等提示
                        scan_indicators = ["已扫码", "扫描成功", "Scan success", "请在手机上确认"]
                        page_text = await page.content()
                        if any(ind in page_text for ind in scan_indicators):
                            old_status = session.status
                            session.status = SessionStatus.SCANNING
                            logger.info(f"[{session.platform}] QR code scanned, waiting for confirmation")
                            # 状态变更，通知前端
                            if old_status != session.status:
                                await self._notify_status_change(session)
                    except Exception:
                        pass
                
                # 自动刷新检测（每10秒一次，且至少等待10秒后开始检测）
                if session.status == SessionStatus.READY and i >= last_auto_refresh_check + auto_refresh_interval:
                    last_auto_refresh_check = i
                    is_expired = await self._detect_qr_expired(session)
                    if is_expired:
                        logger.info(f"[{session.platform}] QR expired detected at {i}s, auto-refreshing")
                        await self._notify_status_change(session)  # 通知过期状态
                        # 触发自动刷新
                        refresh_ok = await self.refresh_qr_code(session.id)
                        if refresh_ok:
                            logger.info(f"[{session.platform}] QR auto-refreshed successfully")
                            # 刷新成功，重新开始轮询（不返回，继续循环）
                            last_auto_refresh_check = 0
                            continue
                        else:
                            logger.warning(f"[{session.platform}] QR auto-refresh failed")
                            session.status = SessionStatus.EXPIRED
                            session.error_msg = "二维码已过期，自动刷新失败，请手动刷新"
                            await self._notify_status_change(session)
                            return
                
                # 每10秒记录一次日志
                if i > 0 and i % 10 == 0:
                    current_url = page.url
                    logger.debug(f"[{session.platform}] Polling login status: {i}s/{platform_timeout}s, url={current_url}")
                
                await asyncio.sleep(1)
            
            # 超时
            logger.warning(f"Login timeout for session {session.id} ({session.platform})")
            session.status = SessionStatus.EXPIRED
            session.error_msg = "登录超时，请刷新二维码重试"
            await self._notify_status_change(session)
            
        except Exception as e:
            logger.error(f"Error polling login status for session {session.id}: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = f"检测登录状态出错: {str(e)[:100]}"
            await self._notify_status_change(session)
    
    async def _handle_login_success(self, session: PersistentSession):
        """处理登录成功，保存 cookie 到对应平台目录"""
        if session.status == SessionStatus.SUCCESS:
            return
        try:
            cookie_filename = f"persistent_{session.id}.json"
            # 保存到对应平台目录
            platform_cookies_path = Path(settings.get_platform_cookies_path(session.platform))
            platform_cookies_path.mkdir(parents=True, exist_ok=True)
            cookie_path = platform_cookies_path / cookie_filename
            await session.context.storage_state(path=str(cookie_path))
            
            session.cookie_file = cookie_filename
            session.status = SessionStatus.SUCCESS
            session._login_success_event.set()
            
            # 尝试获取用户名
            if session.platform == "douyin":
                try:
                    user_name = await session.page.evaluate("""
                        () => {
                            const el = document.querySelector('.user-name, .nickname, [class*="user"]');
                            return el ? el.textContent.trim() : null;
                        }
                    """)
                    session.user_name = user_name
                except:
                    session.user_name = f"抖音账号_{session.id[:8]}"
            elif session.platform == "xhs":
                try:
                    user_name = await session.page.evaluate("""
                        () => {
                            const el = document.querySelector('.user-name, .nickname, [class*="user"], [class*="name"]');
                            return el ? el.textContent.trim() : null;
                        }
                    """)
                    session.user_name = user_name or f"小红书账号_{session.id[:8]}"
                except:
                    session.user_name = f"小红书账号_{session.id[:8]}"
            else:
                session.user_name = f"视频号_{session.id[:8]}"
            
            logger.info(f"Login success for session {session.id}, user: {session.user_name}")
            
        except Exception as e:
            logger.error(f"Error handling login success for session {session.id}: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = str(e)
    
    async def refresh_qr_code(self, session_id: str) -> bool:
        """刷新二维码：删除旧二维码 -> 刷新浏览器页面 -> 截取新的二维码"""
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found for QR refresh")
            return False
        
        if session.status not in [SessionStatus.READY, SessionStatus.EXPIRED, SessionStatus.SCANNING, SessionStatus.FAILED]:
            logger.warning(f"Cannot refresh QR for session {session_id}, current status: {session.status}")
            return False
        
        try:
            logger.info(f"Refreshing QR code for session {session_id} ({session.platform})")
            
            # 步骤1：重置状态并清除就绪标志
            session.status = SessionStatus.INITIALIZING
            session.error_msg = None
            session.qr_ready.clear()
            
            if not session.page:
                logger.error(f"Page not available for session {session_id}")
                session.status = SessionStatus.FAILED
                session.error_msg = "页面不可用"
                session.qr_ready.set()
                return False
            
            # 步骤2：删除旧的二维码缓存文件
            if session.qr_code_path and os.path.exists(session.qr_code_path):
                try:
                    os.remove(session.qr_code_path)
                    logger.info(f"Deleted old QR file for session {session_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete old QR file: {e}")
            
            # 步骤3：刷新浏览器页面获取新二维码
            if session.platform == "douyin":
                logger.info(f"Reloading Douyin page for session {session_id}")
                await goto_with_retry(
                    session.page,
                    "https://creator.douyin.com/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                    retries=3,
                    delay_sec=2.5,
                    log_label=f"Douyin refresh {session_id} goto",
                )
                # 等待登录弹层出现再截码（替代固定 sleep）
                try:
                    await session.page.wait_for_selector(
                        "canvas, text=扫码登录, text=二维码",
                        state="visible",
                        timeout=15000,
                    )
                except Exception:
                    pass
                await self._capture_douyin_qr(session)
            elif session.platform == "tencent":
                logger.info(f"Reloading Tencent page for session {session_id}")
                await goto_with_retry(
                    session.page,
                    "https://channels.weixin.qq.com/login.html",
                    wait_until="domcontentloaded",
                    timeout=60000,
                    retries=3,
                    delay_sec=2.5,
                    log_label=f"Tencent refresh {session_id} goto",
                )
                await asyncio.sleep(1.5)
                await self._capture_tencent_qr(session)
            elif session.platform == "xhs":
                logger.info(f"Reloading XiaoHongShu page for session {session_id}")
                await goto_with_retry(
                    session.page,
                    "https://creator.xiaohongshu.com/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                    retries=3,
                    delay_sec=2.5,
                    log_label=f"XHS refresh {session_id} goto",
                )
                qr_svc = get_qr_login_service()
                await qr_svc._wait_xhs_login_ui(session.page)
                await qr_svc._switch_xhs_to_scan_qr_mode(session.page)
                await self._capture_xhs_qr(session)
            
            # 步骤4：检查截图结果
            if session.status == SessionStatus.READY:
                logger.info(f"QR code refreshed successfully for session {session_id}")
                return True
            else:
                logger.error(f"Failed to capture new QR code for session {session_id}: {session.error_msg}")
                return False
            
        except Exception as e:
            logger.error(f"Error refreshing QR code for session {session_id}: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = user_friendly_uploader_error(
                e, platform_label_for_error(session.platform)
            )
            session.qr_ready.set()
            return False

    _REFRESHABLE_STATUSES = (
        SessionStatus.READY,
        SessionStatus.EXPIRED,
        SessionStatus.SCANNING,
        SessionStatus.FAILED,
    )

    async def refresh_session_qr_wait(self, session_id: str) -> Tuple[bool, Optional[str]]:
        """清除就绪标记、执行 refresh_qr_code 并等待新二维码截图完成。"""
        session = self.sessions.get(session_id)
        if not session:
            return False, "会话不存在"
        session.qr_ready.clear()
        success = await self.refresh_qr_code(session_id)
        if not success:
            return False, session.error_msg or "刷新二维码失败"
        try:
            # 使用 REFRESH_QR_WAIT_TIMEOUT 替代硬编码的 30
            await asyncio.wait_for(session.qr_ready.wait(), timeout=self.REFRESH_QR_WAIT_TIMEOUT)
        except asyncio.TimeoutError:
            return False, "二维码生成超时"
        if session.status == SessionStatus.FAILED:
            return False, session.error_msg or "二维码生成失败"
        return True, None

    async def close_all_sessions(self) -> None:
        """关闭当前所有持久化会话（用于前端离开分发页等）。"""
        ids = list(self.sessions.keys())
        for sid in ids:
            try:
                await self.close_session(sid)
            except Exception as e:
                logger.warning("close_all_sessions failed for %s: %s", sid, e)

    async def refresh_all_sessions(self) -> dict:
        """依次刷新所有处于可刷新状态的会话；SUCCESS/INITIALIZING 等会跳过。"""
        refreshed = 0
        skipped = 0
        errors: List[str] = []
        snapshot = list(self.sessions.items())
        for sid, session in snapshot:
            if session.status not in self._REFRESHABLE_STATUSES:
                skipped += 1
                continue
            ok, err = await self.refresh_session_qr_wait(sid)
            if ok:
                refreshed += 1
            else:
                errors.append(f"{session.platform}:{sid[:8]} — {err or 'unknown'}")
        return {"refreshed": refreshed, "skipped": skipped, "errors": errors}
    
    async def close_session(self, session_id: str):
        """关闭会话（公共接口）"""
        async with self._lock:
            await self._close_session_internal(session_id)
    
    async def _close_session_internal(self, session_id: str):
        """内部关闭会话方法"""
        session = self.sessions.pop(session_id, None)
        if not session:
            return
        
        logger.info(f"Closing persistent session {session_id}")

        # 取消所有跟踪的后台任务
        for task in list(getattr(session, "_background_tasks", set())):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        probe = getattr(session, "_login_probe_task", None)
        if probe and not probe.done():
            probe.cancel()
            try:
                await probe
            except asyncio.CancelledError:
                pass
        
        # 关闭浏览器资源（只关闭 Context 和 Page，不关闭全局 Browser）
        try:
            if session.page:
                await session.page.close()
        except Exception as e:
            logger.debug(f"Error closing page: {e}")
        
        try:
            if session.context:
                await session.context.close()
        except Exception as e:
            logger.debug(f"Error closing context: {e}")
        
        # 注意：不再关闭 browser 和 playwright（全局共享）
        
        # 清理二维码文件
        if session.qr_code_path and os.path.exists(session.qr_code_path):
            try:
                os.remove(session.qr_code_path)
            except Exception as e:
                logger.debug(f"Error removing QR file: {e}")
    
    def get_session(self, session_id: str) -> Optional[PersistentSession]:
        """获取会话"""
        return self.sessions.get(session_id)
    
    def update_heartbeat(self, session_id: str) -> bool:
        """更新心跳时间，同时检查浏览器健康状态
        
        增强功能：
        - 检查 session.page 是否存在且未关闭
        - 检测浏览器进程是否意外崩溃
        - 标记需要恢复的会话
        """
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        # 浏览器健康检查
        if session.page:
            try:
                # 轻量级检查：判断 page 是否已关闭
                if session.page.is_closed():
                    logger.warning(f"Session {session_id} page is closed, marking for recovery")
                    session._needs_recovery = True
                else:
                    # 可选：执行更完整的健康检查（如检查 page.context）
                    # 但 is_closed() 足够轻量且有效
                    pass
            except Exception as e:
                # page 对象异常（可能是浏览器进程崩溃）
                logger.warning(f"Session {session_id} health check failed: {e}")
                session._needs_recovery = True
        elif session.status not in [SessionStatus.SUCCESS, SessionStatus.FAILED]:
            # 非终态但 page 为 None，可能需要恢复
            logger.warning(f"Session {session_id} has no page but status is {session.status}, marking for recovery")
            session._needs_recovery = True
        
        session.last_heartbeat = time.time()
        return True
    
    async def recover_session(self, session_id: str) -> bool:
        """尝试恢复崩溃的会话
        
        当浏览器进程崩溃或 page 被意外关闭时，尝试：
        1. 清理旧的 Context 和 Page
        2. 创建新的 Context 和 Page
        3. 重新加载页面
        
        注意：使用浏览器池化后，无需重启 Browser，只需重建 Context。
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"Cannot recover session {session_id}: session not found")
            return False
        
        if not session._needs_recovery:
            logger.debug(f"Session {session_id} does not need recovery")
            return True
        
        # 检查是否可以恢复
        if session.status in [SessionStatus.SUCCESS, SessionStatus.FAILED]:
            logger.info(f"Session {session_id} is in final state {session.status}, skipping recovery")
            return False
        
        if not session._init_url:
            logger.error(f"Cannot recover session {session_id}: no initial URL saved")
            return False
        
        logger.info(f"Attempting to recover session {session_id} ({session.platform})")
        
        try:
            # 步骤1：清理旧资源
            await self._dispose_session_context_only(session)
            
            # 步骤2：确保全局浏览器实例可用
            browser = await self._ensure_browser()
            
            # 步骤3：创建新的 Context
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
            )
            context = await set_init_script(context)
            if session._attach_speed_routes:
                await attach_douyin_speed_routes(context)
            session.context = context
            
            # 步骤4：创建新的 Page
            page = await context.new_page()
            session.page = page
            
            # 步骤5：重新加载页面
            await goto_with_retry(
                page,
                session._init_url,
                wait_until="domcontentloaded",
                timeout=60000,
                retries=2,
                delay_sec=1.5,
                log_label=f"{session.platform} recovery {session_id} goto",
            )
            
            # 步骤6：重置状态并重新捕获二维码
            session.status = SessionStatus.INITIALIZING
            session.error_msg = None
            session.qr_ready.clear()
            session._needs_recovery = False
            
            # 重新附加登录监听器
            self._attach_login_monitors(session)
            
            # 重新启动登录状态轮询
            self._track_task(session, self._poll_login_status(session))
            
            # 根据平台重新捕获二维码
            if session.platform == "douyin":
                try:
                    await page.wait_for_selector(
                        "canvas, text=扫码登录, text=二维码",
                        state="visible",
                        timeout=10000,
                    )
                except Exception:
                    pass
                await self._capture_douyin_qr(session)
            elif session.platform == "tencent":
                await asyncio.sleep(1)
                await self._capture_tencent_qr(session)
            elif session.platform == "xhs":
                qr_svc = get_qr_login_service()
                await qr_svc._wait_xhs_login_ui(page)
                await qr_svc._switch_xhs_to_scan_qr_mode(page)
                await self._capture_xhs_qr(session)
            
            logger.info(f"Session {session_id} recovered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to recover session {session_id}: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = f"会话恢复失败: {str(e)[:100]}"
            session.qr_ready.set()
            return False
    
    async def get_qr_code_data(self, session_id: str) -> Optional[bytes]:
        """获取二维码图片数据"""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        # 等待二维码就绪
        try:
            # 使用 QR_WAIT_TIMEOUT 替代硬编码的 60
            await asyncio.wait_for(session.qr_ready.wait(), timeout=self.QR_WAIT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"QR ready timeout for session {session_id}")
            return None
        
        # 读取文件
        if session.qr_code_path and os.path.exists(session.qr_code_path):
            try:
                with open(session.qr_code_path, "rb") as f:
                    return f.read()
            except OSError:
                pass
        
        return None


# 全局管理器实例
_persistent_browser_manager: Optional[PersistentBrowserManager] = None


async def get_persistent_browser_manager() -> PersistentBrowserManager:
    """获取持久化浏览器管理器（确保已启动）"""
    global _persistent_browser_manager
    if _persistent_browser_manager is None:
        _persistent_browser_manager = PersistentBrowserManager()
        await _persistent_browser_manager.start()
    return _persistent_browser_manager


def get_persistent_browser_manager_sync() -> Optional[PersistentBrowserManager]:
    """同步获取管理器实例（不确保已启动）"""
    return _persistent_browser_manager
