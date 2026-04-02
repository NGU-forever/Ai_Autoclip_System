# -*- coding: utf-8 -*-
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, Frame
from src.config_manager import config_manager
from src.qr_login.drivers import get_driver
from src.qr_login.success_detector import LoginSuccessDetector
from uploader.conf import settings
from uploader.utils.base_social_media import set_init_script
from uploader.utils.douyin_speed_routes import attach_douyin_speed_routes
from uploader.utils.playwright_net import goto_with_retry, user_friendly_uploader_error, platform_label_for_error

from ..models import PersistentSession, SessionStatus
from ..events import status_emitter
from ..pool import get_browser_pool

logger = logging.getLogger(__name__)

class QRLoginFlow:
    """QR 登录业务流程引擎
    
    职责：
    - 编排登录全生命周期流程 (初始化 -> 捕获码 -> 轮询 -> 成功处理)。
    - 处理自动刷新和恢复逻辑。
    - 状态变更时触发事件。
    """
    
    PLATFORM_URLS = {
        "douyin": "https://creator.douyin.com/",
        "tencent": "https://channels.weixin.qq.com/login.html",
        "xhs": "https://creator.xiaohongshu.com/",
    }

    @classmethod
    async def start_init_platform(cls, session: PersistentSession):
        """异步启动平台初始化任务"""
        try:
            platform = session.platform
            logger.info(f"Initializing {platform} browser for session {session.id}")
            
            # 1. 准备浏览器上下文
            url = cls.PLATFORM_URLS.get(platform)
            if not url:
                raise ValueError(f"Unknown platform: {platform}")
            
            page = await cls._init_context_and_page(session, url)
            
            # 2. 获取 Driver 执行 DOM 操作
            driver = get_driver(platform)
            await driver.prepare_login_page(page)
            
            # 3. 捕获二维码
            ok = await driver.capture_qr_code(page, session.qr_code_path)
            png_ok = ok and os.path.exists(session.qr_code_path) and os.path.getsize(session.qr_code_path) >= 200
            
            if not png_ok:
                session.status = SessionStatus.FAILED
                session.error_msg = "二维码生成失败"
                session.qr_ready.set()
                await status_emitter.emit(session)
                return
            
            # 4. 二维码就绪
            session.status = SessionStatus.READY
            session.qr_ready.set()
            logger.info(f"{platform} QR code captured for session {session.id}")
            await status_emitter.emit(session)
            
            # 5. 启动状态轮询
            cls._attach_login_monitors(session)
            # 注意：此处任务追踪应由 Manager 负责，Flow 只负责执行逻辑
            asyncio.create_task(cls.poll_login_status(session, driver))
            
        except Exception as e:
            logger.error(f"Error during {platform} initialization: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = user_friendly_uploader_error(e, platform_label_for_error(platform))
            session.qr_ready.set()
            await status_emitter.emit(session)

    @classmethod
    async def _init_context_and_page(cls, session: PersistentSession, url: str) -> Page:
        """从资源池获取 Context 和 Page 并加载目标 URL"""
        pool = await get_browser_pool()
        
        # 保存初始化参数用于恢复
        session._init_url = url
        session._attach_speed_routes = (session.platform == "douyin")
        
        context = await pool.create_context()
        context = await set_init_script(context)
        if session._attach_speed_routes:
            await attach_douyin_speed_routes(context)
        
        session.context = context
        page = await context.new_page()
        session.page = page
        
        await goto_with_retry(
            page, url, wait_until="domcontentloaded", timeout=60000, 
            retries=3, delay_sec=2.5, log_label=f"{session.platform} session {session.id} init"
        )
        return page

    @classmethod
    async def poll_login_status(cls, session: PersistentSession, driver) -> None:
        """执行扫码状态轮询"""
        try:
            platform_timeout = settings.get_platform_qr_validity(session.platform)
            auto_refresh_interval = 10
            last_auto_refresh_check = 0
            
            for i in range(platform_timeout):
                if session.status in [SessionStatus.SUCCESS, SessionStatus.FAILED]:
                    return
                if session._needs_recovery:
                    return
                
                page = session.page
                if not page: return
                
                # 1. Driver 检测扫码状态
                scan_status = await driver.detect_scan_status(page)
                if scan_status == 'scanning' and session.status != SessionStatus.SCANNING:
                    session.status = SessionStatus.SCANNING
                    logger.info(f"[{session.platform}] QR code scanned, waiting confirmation")
                    await status_emitter.emit(session)
                
                elif scan_status == 'expired' and session.status == SessionStatus.READY:
                    logger.info(f"[{session.platform}] QR expired detected by Driver")
                    if await driver.refresh_qr_code(page):
                        last_auto_refresh_check = 0
                        continue
                    else:
                        session.status = SessionStatus.EXPIRED
                        session.error_msg = "二维码已过期"
                        await status_emitter.emit(session)
                        return
                
                # 2. 统一成功判定
                if await LoginSuccessDetector.check(page, session.platform):
                    logger.info(f"[{session.platform}] ✅ Login SUCCESS detected!")
                    session.user_name = await driver.get_user_name(page)
                    await cls.handle_login_success(session)
                    return
                
                # 3. 定期自动刷新检测
                if session.status == SessionStatus.READY and i >= last_auto_refresh_check + auto_refresh_interval:
                    last_auto_refresh_check = i
                    if await cls._detect_raw_qr_expired(session):
                        await status_emitter.emit(session)
                        if await driver.refresh_qr_code(page):
                            last_auto_refresh_check = 0
                            continue
                        else:
                            session.status = SessionStatus.EXPIRED
                            session.error_msg = "二维码已过期，自动刷新失败"
                            await status_emitter.emit(session)
                            return
                
                await asyncio.sleep(1)
            
            # 4. 超时处理
            session.status = SessionStatus.EXPIRED
            session.error_msg = "登录超时，请刷新预览"
            await status_emitter.emit(session)
            
        except Exception as e:
            logger.error(f"Error polling login status for session {session.id}: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = f"检测登录状态出错: {str(e)[:100]}"
            await status_emitter.emit(session)

    @classmethod
    async def handle_login_success(cls, session: PersistentSession):
        """处理登录成功：保存 Cookie 并注册账号"""
        try:
            # 保存 Cookie
            cookie_file = f"persistent_{session.id}.json"
            platform_cookies_path = Path(settings.get_platform_cookies_path(session.platform))
            platform_cookies_path.mkdir(parents=True, exist_ok=True)
            cookie_path = platform_cookies_path / cookie_file
            
            await session.context.storage_state(path=str(cookie_path))
            session.cookie_file = cookie_file
            session.status = SessionStatus.SUCCESS
            session._login_success_event.set()
            
            # 自动化注册到系统
            try:
                from src.upload.service import UploaderService
                UploaderService().update_account_cookie(
                    platform=session.platform,
                    user_name=session.user_name,
                    cookie_filename=session.cookie_file,
                )
                logger.info(f"Successfully registered account {session.user_name}")
            except Exception as e:
                logger.error(f"Failed to auto-register account: {e}")
                
            await status_emitter.emit(session)
            
        except Exception as e:
            logger.error(f"Error handling login success: {e}")
            session.status = SessionStatus.FAILED
            session.error_msg = str(e)
            await status_emitter.emit(session)

    @staticmethod
    async def _detect_raw_qr_expired(session: PersistentSession) -> bool:
        """底层检查页面文本和选择器以判断二维码是否过期"""
        if not session.page: return False
        try:
            page = session.page
            page_text = await page.content()
            if any(kw in page_text for kw in settings.qr_expired_keywords):
                return True
            
            selectors = settings.qr_expired_selectors.get(session.platform, [])
            for s in selectors:
                if await page.is_visible(s):
                    return True
            return False
        except:
            return False

    @classmethod
    def _attach_login_monitors(cls, session: PersistentSession):
        """附加页面导航监听器"""
        page = session.page
        if not page or session._login_monitors_attached:
            return
        session._login_monitors_attached = True

        def on_nav(frame: Frame):
            if session.status in (SessionStatus.SUCCESS, SessionStatus.FAILED, SessionStatus.INITIALIZING):
                return
            if frame == page.main_frame:
                cls._schedule_login_probe(session)

        page.on("framenavigated", on_nav)
        page.on("load", lambda _: cls._schedule_login_probe(session))

    @classmethod
    def _schedule_login_probe(cls, session: PersistentSession):
        async def _probe():
            await asyncio.sleep(0.5)
            if session.status not in (SessionStatus.READY, SessionStatus.SCANNING, SessionStatus.EXPIRED):
                return
            if await LoginSuccessDetector.check(session.page, session.platform):
                await cls.handle_login_success(session)
        
        asyncio.create_task(_probe())
