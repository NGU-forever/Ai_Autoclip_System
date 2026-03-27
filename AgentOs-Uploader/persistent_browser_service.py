# -*- coding: utf-8 -*-
"""
持久化浏览器会话服务
用于后台常驻浏览器实例，支持二维码刷新而无需重启浏览器
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

from playwright.async_api import async_playwright, Browser, BrowserContext, Frame, Page

from src.config import settings
from uploader.conf import LOCAL_CHROME_PATH
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
    platform: str  # douyin, tencent
    status: SessionStatus
    browser: Optional[Browser] = None
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


class PersistentBrowserManager:
    """持久化浏览器管理器"""
    
    # 心跳超时时间（秒）
    HEARTBEAT_TIMEOUT = 30
    # 心跳检查间隔（秒）
    HEARTBEAT_CHECK_INTERVAL = 10
    # 二维码有效期（秒）
    QR_CODE_VALIDITY = 300  # 5分钟
    
    def __init__(self):
        self.sessions: Dict[str, PersistentSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
    
    async def start(self):
        """启动管理器，开始心跳检查任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("PersistentBrowserManager started")
    
    async def stop(self):
        """停止管理器，关闭所有会话"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有会话
        for session in list(self.sessions.values()):
            await self.close_session(session.id)
        
        logger.info("PersistentBrowserManager stopped")
    
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
        """清理心跳超时的会话"""
        now = time.time()
        expired_sessions = []
        
        for session_id, session in self.sessions.items():
            if now - session.last_heartbeat > self.HEARTBEAT_TIMEOUT:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            logger.info(f"Session {session_id} heartbeat timeout, closing")
            await self.close_session(session_id)
    
    def _ensure_dirs(self):
        """确保目录存在"""
        os.makedirs(settings.uploader_cookies_path, exist_ok=True)
        qr_dir = Path(settings.storage_root) / "uploader" / "qr_codes"
        os.makedirs(qr_dir, exist_ok=True)
        return qr_dir
    
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
            
            session_id = str(uuid.uuid4())
            qr_dir = self._ensure_dirs()
            
            session = PersistentSession(
                id=session_id,
                platform=platform,
                status=SessionStatus.INITIALIZING,
                qr_code_path=str(qr_dir / f"persistent_{session_id}.png")
            )
            self.sessions[session_id] = session
            
            # 启动异步任务初始化浏览器
            asyncio.create_task(self._init_browser(session))
            
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
        """关闭会话内 Playwright 资源，不从 sessions 中移除（用于 FAILED 等状态释放进程内资源）。"""
        try:
            if session.page:
                await session.page.close()
        except Exception as e:
            logger.debug("dispose: page close: %s", e)
        session.page = None
        try:
            if session.context:
                await session.context.close()
        except Exception as e:
            logger.debug("dispose: context close: %s", e)
        session.context = None
        try:
            if session.browser:
                await session.browser.close()
        except Exception as e:
            logger.debug("dispose: browser close: %s", e)
        session.browser = None
        try:
            pw = getattr(session, "_playwright", None)
            if pw is not None:
                await pw.stop()
        except Exception as e:
            logger.debug("dispose: playwright stop: %s", e)
        setattr(session, "_playwright", None)
    
    async def _init_douyin(self, session: PersistentSession):
        """初始化抖音浏览器"""
        logger.info(f"Initializing Douyin browser for session {session.id}")

        playwright = await async_playwright().start()
        session._playwright = playwright

        launch_options = merge_chromium_launch_options({"headless": True})
        if LOCAL_CHROME_PATH:
            launch_options["executable_path"] = LOCAL_CHROME_PATH

        browser = await playwright.chromium.launch(**launch_options)
        session.browser = browser

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        context = await set_init_script(context)
        await attach_douyin_speed_routes(context)
        session.context = context

        page = await context.new_page()
        session.page = page

        try:
            logger.info("Navigating to Douyin creator page")
            await goto_with_retry(
                page,
                "https://creator.douyin.com/",
                wait_until="domcontentloaded",
                timeout=60000,
                retries=3,
                delay_sec=2.5,
                log_label=f"Douyin session {session.id} goto",
            )
            await asyncio.sleep(2.8)

            # 捕获二维码
            await self._capture_douyin_qr(session)

            self._attach_login_monitors(session)
            # 开始轮询登录状态
            asyncio.create_task(self._poll_login_status(session))

        except Exception as e:
            logger.error(f"Error during Douyin initialization: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = user_friendly_uploader_error(e, "抖音创作者")
            await self._dispose_session_browser_resources(session)
            session.qr_ready.set()
    
    async def _capture_douyin_qr(self, session: PersistentSession):
        """捕获抖音二维码（专用 prime + 中心 canvas 策略，避免作品体裁轮播误识别）"""
        qr_service = get_qr_login_service()
        ok = await qr_service._capture_douyin_login_qr(
            session.page,
            session.qr_code_path,
        )
        png_ok = (
            ok
            and os.path.exists(session.qr_code_path)
            and os.path.getsize(session.qr_code_path) >= 200
        )
        if png_ok:
            session.status = SessionStatus.READY
            session.qr_ready.set()
            logger.info(f"Douyin QR code captured for session {session.id}")
        else:
            session.status = SessionStatus.FAILED
            session.error_msg = "二维码生成失败"
            session.qr_ready.set()
    
    async def _init_tencent(self, session: PersistentSession):
        """初始化视频号浏览器"""
        logger.info(f"Initializing Tencent browser for session {session.id}")
        
        playwright = await async_playwright().start()
        session._playwright = playwright
        
        launch_options = merge_chromium_launch_options({"headless": True})
        if LOCAL_CHROME_PATH:
            launch_options["executable_path"] = LOCAL_CHROME_PATH
        
        browser = await playwright.chromium.launch(**launch_options)
        session.browser = browser
        
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        context = await set_init_script(context)
        session.context = context
        
        page = await context.new_page()
        session.page = page
        
        try:
            login_url = "https://channels.weixin.qq.com/login.html"
            logger.info(f"Navigating to {login_url}")
            await goto_with_retry(
                page,
                login_url,
                wait_until="domcontentloaded",
                timeout=60000,
                retries=3,
                delay_sec=2.5,
                log_label=f"Tencent session {session.id} goto",
            )
            await asyncio.sleep(1)
            
            # 捕获二维码
            await self._capture_tencent_qr(session)

            self._attach_login_monitors(session)
            # 开始轮询登录状态
            asyncio.create_task(self._poll_login_status(session))
            
        except Exception as e:
            logger.error(f"Error during Tencent initialization: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = user_friendly_uploader_error(e, "微信视频号")
            await self._dispose_session_browser_resources(session)
            session.qr_ready.set()
    
    async def _capture_tencent_qr(self, session: PersistentSession):
        """捕获视频号二维码（复用原逻辑）"""
        qr_service = get_qr_login_service()
        ok = await qr_service._capture_login_qr_fast(
            session.page, session.qr_code_path, "Tencent"
        )
        
        png_ok = (
            ok
            and os.path.exists(session.qr_code_path)
            and os.path.getsize(session.qr_code_path) >= 200
        )
        
        if png_ok:
            session.status = SessionStatus.READY
            session.qr_ready.set()
            logger.info(f"Tencent QR code captured for session {session.id}")
        else:
            session.status = SessionStatus.FAILED
            session.error_msg = "二维码生成失败"
            session.qr_ready.set()

    async def _init_xhs(self, session: PersistentSession):
        """初始化小红书浏览器"""
        logger.info(f"Initializing XiaoHongShu browser for session {session.id}")
        
        playwright = await async_playwright().start()
        session._playwright = playwright
        
        launch_options = merge_chromium_launch_options({"headless": True})
        if LOCAL_CHROME_PATH:
            launch_options["executable_path"] = LOCAL_CHROME_PATH
        
        browser = await playwright.chromium.launch(**launch_options)
        session.browser = browser
        
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        context = await set_init_script(context)
        session.context = context
        
        page = await context.new_page()
        session.page = page
        
        try:
            logger.info("Navigating to XiaoHongShu creator page")
            await goto_with_retry(
                page,
                "https://creator.xiaohongshu.com/",
                wait_until="domcontentloaded",
                timeout=60000,
                retries=3,
                delay_sec=2.5,
                log_label=f"XHS session {session.id} goto",
            )
            qr_svc = get_qr_login_service()
            await qr_svc._wait_xhs_login_ui(page)
            await qr_svc._switch_xhs_to_scan_qr_mode(page)

            # 捕获二维码
            await self._capture_xhs_qr(session)

            self._attach_login_monitors(session)
            # 开始轮询登录状态
            asyncio.create_task(self._poll_login_status(session))
            
        except Exception as e:
            logger.error(f"Error during XiaoHongShu initialization: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = user_friendly_uploader_error(e, "小红书创作者")
            await self._dispose_session_browser_resources(session)
            session.qr_ready.set()

    async def _capture_xhs_qr(self, session: PersistentSession):
        """捕获小红书二维码（复用原逻辑）"""
        qr_service = get_qr_login_service()
        panel_rect = await qr_service.get_xhs_login_panel_viewport_rect(session.page)
        ok = await qr_service._capture_login_qr_fast(
            session.page,
            session.qr_code_path,
            "XHS",
            min_qr_area=120 * 120,
            initial_sleep=0.2,
            poll_interval=0.18,
            pre_screenshot_sleep=0.06,
            container_rect=panel_rect,
        )
        
        png_ok = (
            ok
            and os.path.exists(session.qr_code_path)
            and os.path.getsize(session.qr_code_path) >= 200
        )
        
        if png_ok:
            session.status = SessionStatus.READY
            session.qr_ready.set()
            logger.info(f"XiaoHongShu QR code captured for session {session.id}")
        else:
            session.status = SessionStatus.FAILED
            session.error_msg = "二维码生成失败"
            session.qr_ready.set()

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
    _LOGIN_SUCCESS_URL_PATTERNS = {
        "douyin": [
            "creator.douyin.com/creator-micro",
            "creator.douyin.com/home",
            "creator.douyin.com/dashboard",
        ],
        "tencent": [
            "#/platform",
            "#/creator",
            "platform/post/create",
            "platform/post/list",
            "channels.weixin.qq.com/platform",
        ],
        "xhs": [
            "creator.xiaohongshu.com/creator-micro",
            "creator.xiaohongshu.com/publish",
        ],
    }
    
    # DOM 选择器：检测登录成功后页面上的用户相关元素
    _LOGIN_SUCCESS_DOM_SELECTORS = {
        "douyin": [
            ".user-name",
            ".avatar",
            "[data-e2e='user-name']",
            ".user-info",
            ".nickname",
            "[class*='userName']",
            "[class*='avatar']",
            "div[class*='header'] img",  # 头像图片
            "span[class*='name']",
        ],
        "tencent": [
            ".user-avatar",
            ".creator-center",
            ".user-info",
            ".nickname",
            "[class*='avatar']",
            "[class*='userName']",
            ".header-user",
            "img[class*='avatar']",
        ],
        "xhs": [
            ".user-name",
            ".nickname",
            "[class*='avatar']",
            "[class*='userName']",
            "[class*='nickName']",
            ".user-info",
            "img[class*='avatar']",
            "span[class*='name']",
        ],
    }
    
    # Cookie 名称：检测登录态的关键 cookie
    _LOGIN_SUCCESS_COOKIES = {
        "douyin": ["sessionid", "sid_guard", "sid_tt", "uid_tt", "odin_tt"],
        "tencent": ["wxtokenkey", "wxuin", "wxsid", "pass_ticket"],
        "xhs": ["web_session", "webId", "xhsTracker", "userId"],
    }

    async def _check_login_success_indicators(self, session: PersistentSession) -> bool:
        """
        综合检测登录成功标志
        使用多种检测方式提高准确性：URL 匹配、DOM 元素检测、Cookie 检测
        返回 True 表示检测到登录成功
        """
        page = session.page
        if not page:
            return False
        
        platform = session.platform
        current_url = page.url

        if self._url_hard_logged_in(platform, current_url):
            logger.info(
                "[%s] Hard URL indicates logged in (session=%s): %s",
                platform,
                session.id,
                current_url,
            )
            return True

        ul = current_url.lower()
        # 勿用宽泛子串「login」屏蔽视频号：成功态仍为 login.html#/platform/...
        is_login_page = False
        if platform == "tencent" and "channels.weixin.qq.com/login.html" in ul:
            frag = (current_url.split("#", 1)[-1] if "#" in current_url else "").lower()
            is_login_page = not ("platform" in frag or "post" in frag)
        else:
            is_login_page = any(
                x in ul for x in ("passport", "qrconnect", "open.weixin.qq.com", "open.weixin")
            ) or ("signin" in ul)
            if "login" in ul and not any(
                h in ul for h in ("#/platform", "#/creator", "creator-micro/content/upload")
            ):
                is_login_page = True
        
        score = 0  # 置信度分数
        detected_methods = []
        
        # 1. URL 检测
        url_patterns = self._LOGIN_SUCCESS_URL_PATTERNS.get(platform, [])
        url_matched = any(pattern in current_url for pattern in url_patterns)
        if url_matched and not is_login_page:
            score += 2
            detected_methods.append("url")
            logger.debug(f"[{platform}] URL pattern matched: {current_url}")
        
        # 2. DOM 元素检测
        dom_selectors = self._LOGIN_SUCCESS_DOM_SELECTORS.get(platform, [])
        dom_matched = False
        for selector in dom_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    # 检查元素是否可见且有内容
                    is_visible = await element.is_visible()
                    if is_visible:
                        text = await element.text_content()
                        # 小红书等平台登录后会有特定文字提示
                        if text and 0 < len(text.strip()) <= 64:
                            dom_matched = True
                            logger.debug(f"[{platform}] DOM element matched: {selector}, text: {text.strip()[:20]}")
                            break
            except Exception:
                continue
        
        if dom_matched:
            score += 3
            detected_methods.append("dom")
        
        # 3. Cookie 检测
        cookie_names = self._LOGIN_SUCCESS_COOKIES.get(platform, [])
        cookie_matched = False
        try:
            cookies = await page.context.cookies()
            cookie_dict = {c["name"]: c for c in cookies}
            matched_cookies = [name for name in cookie_names if name in cookie_dict]
            if matched_cookies:
                # 检查 cookie 是否有值且未过期
                valid_cookies = 0
                for name in matched_cookies:
                    cookie = cookie_dict[name]
                    if cookie.get("value") and len(cookie["value"]) > 5:
                        # 检查过期时间（如果存在）
                        expires = cookie.get("expires", -1)
                        if expires == -1 or expires > time.time():
                            valid_cookies += 1
                
                if valid_cookies >= 1:
                    cookie_matched = True
                    logger.debug(f"[{platform}] Cookies matched: {matched_cookies}")
        except Exception as e:
            logger.debug(f"[{platform}] Cookie check error: {e}")
        
        if cookie_matched:
            score += 2
            detected_methods.append("cookie")
        
        # 4. 页面标题检测（辅助）
        try:
            title = await page.title()
            title_indicators = {
                "douyin": ["创作者", "抖音", "创作服务平台"],
                "tencent": ["视频号", "创作者", "微信"],
                "xhs": ["小红书", "创作", "创作者中心"],
            }
            title_keywords = title_indicators.get(platform, [])
            if any(kw in title for kw in title_keywords):
                # 排除登录相关标题
                if not any(word in title for word in ["登录", "扫码", "Login", "Sign"]):
                    score += 1
                    detected_methods.append("title")
                    logger.debug(f"[{platform}] Title matched: {title}")
        except Exception:
            pass
        
        # 判断登录成功：需要满足以下条件之一
        # 1. 总分 >= 3
        # 2. DOM 元素检测通过 + 任意其他检测（因为 DOM 元素最可靠）
        # 3. Cookie 检测通过 + URL 匹配（Cookie + URL 也很可靠）
        # 4. 非登录页且关键 Cookie 已就绪（避免仅靠 Cookie 分数不足导致不落盘 storage_state）
        is_logged_in = (
            score >= 3
            or ("dom" in detected_methods and len(detected_methods) >= 2)
            or ("cookie" in detected_methods and "url" in detected_methods)
            or (cookie_matched and not is_login_page)
        )
        
        if is_logged_in:
            logger.info(
                f"[{platform}] Login success detected for session {session.id}, "
                f"score={score}, methods={detected_methods}, url={current_url}"
            )
        
        return is_logged_in

    async def _poll_login_status(self, session: PersistentSession):
        """轮询检查登录状态"""
        try:
            for i in range(300):  # 最多5分钟
                # 检查会话是否还存在
                if session.id not in self.sessions:
                    logger.info(f"Session {session.id} no longer exists, stopping poll")
                    return
                
                # 检查是否已登录成功
                if session.status == SessionStatus.SUCCESS:
                    return
                
                page = session.page
                if not page:
                    logger.warning(f"Page not available for session {session.id}")
                    return
                
                # 使用增强的检测方法
                is_logged_in = await self._check_login_success_indicators(session)
                if is_logged_in:
                    await self._handle_login_success(session)
                    return
                
                # 检查是否已扫码（等待确认）
                if session.status == SessionStatus.READY:
                    try:
                        # 检测"已扫码"或"扫描成功"等提示
                        scan_indicators = ["已扫码", "扫描成功", "Scan success", "请在手机上确认"]
                        page_text = await page.content()
                        if any(ind in page_text for ind in scan_indicators):
                            session.status = SessionStatus.SCANNING
                            logger.info(f"[{session.platform}] QR code scanned, waiting for confirmation")
                    except Exception:
                        pass
                
                # 每10秒记录一次日志
                if i > 0 and i % 10 == 0:
                    current_url = page.url
                    logger.debug(f"[{session.platform}] Polling login status: {i}s, url={current_url}")
                
                await asyncio.sleep(1)
            
            # 超时
            logger.warning(f"Login timeout for session {session.id} ({session.platform})")
            session.status = SessionStatus.EXPIRED
            session.error_msg = "登录超时，请刷新二维码重试"
            
        except Exception as e:
            logger.error(f"Error polling login status for session {session.id}: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = f"检测登录状态出错: {str(e)[:100]}"
    
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
                await asyncio.sleep(2.8)
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
            await asyncio.wait_for(session.qr_ready.wait(), timeout=30)
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

        probe = getattr(session, "_login_probe_task", None)
        if probe and not probe.done():
            probe.cancel()
            try:
                await probe
            except asyncio.CancelledError:
                pass
        
        # 关闭浏览器资源
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
        
        try:
            if session.browser:
                await session.browser.close()
        except Exception as e:
            logger.debug(f"Error closing browser: {e}")
        
        try:
            if hasattr(session, '_playwright'):
                await session._playwright.stop()
        except Exception as e:
            logger.debug(f"Error stopping playwright: {e}")
        
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
        """更新心跳时间"""
        session = self.sessions.get(session_id)
        if session:
            session.last_heartbeat = time.time()
            return True
        return False
    
    async def get_qr_code_data(self, session_id: str) -> Optional[bytes]:
        """获取二维码图片数据"""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        # 等待二维码就绪
        try:
            await asyncio.wait_for(session.qr_ready.wait(), timeout=60)
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
