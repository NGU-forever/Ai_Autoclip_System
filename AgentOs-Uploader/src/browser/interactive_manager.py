# -*- coding: utf-8 -*-
"""
交互式浏览器管理器（简化版）

直接打开真实浏览器窗口让用户操作，后端只负责：
- 启动浏览器（有头模式）
- 定期检测登录状态
- 自动保存 cookie
- 关闭浏览器
"""

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from playwright.async_api import async_playwright

from src.config import settings
from src.db.repository import AccountRepository
from src.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class InteractiveBrowserManager:
    """交互式浏览器管理器（单例）
    
    直接打开真实浏览器窗口，用户自行操作登录。
    """
    
    _instance: Optional['InteractiveBrowserManager'] = None
    _lock = asyncio.Lock()
    
    # 平台登录页 URL
    PLATFORM_URLS = {
        "douyin": "https://creator.douyin.com/",
        "tencent": "https://channels.weixin.qq.com/login.html",
        "xhs": "https://creator.xiaohongshu.com/",
    }
    
    # 创作者平台 URL（登录成功后跳转）
    CREATOR_URLS = {
        "douyin": "https://creator.douyin.com/creator-micro/content/upload",
        "tencent": "https://channels.weixin.qq.com/platform",
        "xhs": "https://creator.xiaohongshu.com/publish/publish",
    }
    
    # 登录检测的关键 cookie
    PLATFORM_KEY_COOKIES = {
        "douyin": {"sessionid", "sid_guard", "sid_tt", "odin_tt"},
        "tencent": {"sessionid", "pgv_pvid", "wxtokenkey"},
        "xhs": {"web_session", "websectiga", "xhsTracker"},
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(InteractiveBrowserManager, cls).__new__(cls)
            cls._instance.sessions: Dict[str, dict] = {}
            cls._instance._cleanup_task: Optional[asyncio.Task] = None
        return cls._instance
    
    @classmethod
    async def get_instance(cls) -> 'InteractiveBrowserManager':
        """获取管理器单例"""
        return cls()
    
    async def start(self):
        """启动管理器"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("InteractiveBrowserManager started")
    
    async def stop(self):
        """停止管理器并关闭所有浏览器"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有会话
        for session_id in list(self.sessions.keys()):
            await self.close_session(session_id)
        
        logger.info("InteractiveBrowserManager stopped")
    
    async def create_session(self, platform: str, existing_account: Optional[dict] = None) -> dict:
        """创建新的交互式浏览器会话
        
        Args:
            platform: 平台名称 (douyin, tencent, xhs)
            existing_account: 如果提供了已登录账号，直接打开创作者平台
            
        Returns:
            会话信息字典
        """
        async with self._lock:
            # 检查是否已有同平台的活跃会话或正在初始化的会话
            existing_sessions = [
                sid for sid, s in self.sessions.items()
                if s['platform'] == platform and s['status'] not in ('closed', 'failed')
            ]
            for sid in existing_sessions:
                logger.info(f"Closing existing session for {platform}: {sid}")
                await self._close_session_internal(sid)
            
            session_id = str(uuid.uuid4())
            
            session = {
                'id': session_id,
                'platform': platform,
                'status': 'initializing',
                'browser': None,
                'context': None,
                'page': None,
                'cookie_file': None,
                'user_name': None,
                'account_id': existing_account.get('id') if existing_account else None,
                'error_msg': None,
                'created_at': time.time(),
                'last_heartbeat': time.time(),
                'login_detected': False,
            }
            
            self.sessions[session_id] = session
            
            # 启动浏览器（在锁内完成初始化，防止竞态条件）
            # 只启动到浏览器创建完成，导航作为后台任务
            try:
                playwright = await async_playwright().start()
                session['_playwright'] = playwright
                
                # 检测是否需要使用 headless 模式
                headless = self._should_use_headless()
                
                # 启动浏览器（非 headless 失败时自动回退到 headless）
                browser = None
                try:
                    browser = await playwright.chromium.launch(
                        headless=headless,
                        args=[
                            '--window-size=1400,900',
                            '--disable-blink-features=AutomationControlled',
                        ]
                    )
                    if not headless:
                        logger.info(f"浏览器已启动（有头模式），session: {session_id}")
                except Exception as launch_err:
                    err_msg = str(launch_err).lower()
                    # 如果是图形环境相关错误，尝试回退到 headless
                    if not headless and ('display' in err_msg or 'x server' in err_msg or 
                                         'headless' in err_msg or 'xvfb' in err_msg):
                        logger.warning(f"无法启动图形界面浏览器，回退到 headless 模式: {launch_err}")
                        browser = await playwright.chromium.launch(
                            headless=True,
                            args=[
                                '--window-size=1400,900',
                                '--disable-blink-features=AutomationControlled',
                            ]
                        )
                        session['error_msg'] = "当前运行在 headless 模式，浏览器窗口不可见"
                    else:
                        raise  # 其他错误直接抛出
                
                session['browser'] = browser
                
                # 创建上下文
                context = await browser.new_context(
                    viewport={'width': 1400, 'height': 900},
                    locale='zh-CN',
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                )
                session['context'] = context
                
                page = await context.new_page()
                session['page'] = page
                
                logger.info(f"Created interactive browser session {session_id} for {platform}")
                
            except Exception as e:
                logger.error(f"Failed to create browser for session {session_id}: {e}")
                error_msg = str(e)
                if "Missing X server" in error_msg or "$DISPLAY" in error_msg:
                    error_msg = "无法启动图形界面：Docker 容器缺少 X Server。请确保 Dockerfile 已安装 xvfb 且启动时设置了 DISPLAY 环境变量。"
                session['status'] = 'failed'
                session['error_msg'] = error_msg
                # 清理资源
                await self._close_session_internal(session_id)
                return {
                    'sessionId': session_id,
                    'platform': platform,
                    'status': 'failed',
                    'error': error_msg,
                }
        
        # 锁外执行导航（可能耗时较长）
        asyncio.create_task(self._navigate_and_monitor(session, existing_account))
        
        return {
            'sessionId': session_id,
            'platform': platform,
            'status': 'initializing',
        }
    
    async def _navigate_and_monitor(self, session: dict, existing_account: Optional[dict] = None):
        """导航到目标页面并启动登录检测"""
        try:
            page = session.get('page')
            if not page or page.is_closed():
                logger.warning(f"Session {session['id']} page already closed before navigation")
                return
            
            # 决定打开哪个页面
            if existing_account:
                url = self.CREATOR_URLS.get(session['platform'])
                session['status'] = 'creator_platform'
                session['user_name'] = existing_account.get('user_name')
                logger.info(f"Opening creator platform for existing account: {existing_account.get('user_name')}")
            else:
                url = self.PLATFORM_URLS.get(session['platform'])
                session['status'] = 'waiting_login'
            
            if not url:
                raise ValueError(f"Unknown platform: {session['platform']}")
            
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)
            
            logger.info(f"Browser navigated for session {session['id']}, url: {url}")
            
            # 如果不是已有账号，启动登录检测任务
            if not existing_account:
                asyncio.create_task(self._login_detect_loop(session))
                
        except Exception as e:
            logger.error(f"Failed to navigate for session {session['id']}: {e}")
            if session.get('status') != 'closed':
                session['status'] = 'failed'
                session['error_msg'] = str(e)
    
    async def _login_detect_loop(self, session: dict):
        """登录检测循环"""
        try:
            while session['status'] not in ('closed', 'failed', 'creator_platform'):
                page = session.get('page')
                if not page or page.is_closed():
                    break
                
                # 检测是否已登录
                is_logged_in = await self._check_login_status(session)
                
                if is_logged_in and not session['login_detected']:
                    logger.info(f"Login detected for session {session['id']}")
                    session['login_detected'] = True
                    session['status'] = 'logged_in'
                    
                    # 保存 cookie
                    await self._save_session_cookies(session)
                    
                    # 跳转到创作者平台
                    await self._navigate_to_creator_platform(session)
                
                # 每秒检测一次
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.debug(f"Login detect loop cancelled for session {session['id']}")
        except Exception as e:
            logger.error(f"Login detect loop error for session {session['id']}: {e}")
    
    async def _check_login_status(self, session: dict) -> bool:
        """检查登录状态"""
        try:
            context = session.get('context')
            if not context:
                return False
            
            cookies = await context.cookies()
            cookie_names = {c.get("name", "") for c in cookies}
            
            key_cookies = self.PLATFORM_KEY_COOKIES.get(session['platform'], set())
            
            # 检查是否有任意一个关键 cookie
            has_key_cookie = bool(key_cookies & cookie_names)
            
            # 额外检查：页面 URL
            url_check = False
            page = session.get('page')
            if page:
                url = page.url
                platform = session['platform']
                if platform == "douyin":
                    url_check = "creator.douyin.com" in url and "login" not in url.lower()
                elif platform == "tencent":
                    url_check = "channels.weixin.qq.com/platform" in url
                elif platform == "xhs":
                    url_check = "creator.xiaohongshu.com" in url and "login" not in url.lower()
            
            return has_key_cookie or url_check
            
        except Exception as e:
            logger.debug(f"Check login status failed: {e}")
            return False
    
    async def _save_session_cookies(self, session: dict):
        """保存会话的 cookies 到文件"""
        try:
            context = session.get('context')
            if not context:
                return
            
            # 保存 storage state
            cookie_file = f"interactive_{session['id']}.json"
            platform_cookies_path = Path(settings.get_platform_cookies_path(session['platform']))
            platform_cookies_path.mkdir(parents=True, exist_ok=True)
            cookie_path = platform_cookies_path / cookie_file
            
            await context.storage_state(path=str(cookie_path))
            
            session['cookie_file'] = cookie_file
            
            # 尝试获取用户名
            user_name = await self._get_user_name(session)
            session['user_name'] = user_name
            
            # 保存到数据库
            await self._save_account_to_db(session)
            
            logger.info(f"Cookies saved for session {session['id']}, user: {user_name}")
            
        except Exception as e:
            logger.error(f"Save cookies failed for session {session['id']}: {e}")
    
    async def _get_user_name(self, session: dict) -> Optional[str]:
        """从页面获取用户名"""
        try:
            page = session.get('page')
            if not page:
                return None
            
            # 平台特定的选择器
            selectors = {
                "douyin": [
                    '.user-name', '.nickname', '[class*="userName"]', '[class*="user-name"]',
                ],
                "tencent": [
                    '.nick-name', '.username', '[class*="nickName"]',
                ],
                "xhs": [
                    '.user-name', '.nickname', '[class*="userName"]',
                ],
            }
            
            platform_selectors = selectors.get(session['platform'], [])
            
            for selector in platform_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        text = await element.text_content()
                        if text and text.strip():
                            return text.strip()
                except:
                    continue
            
            return None
            
        except Exception as e:
            logger.debug(f"Get user name failed: {e}")
            return None
    
    async def _save_account_to_db(self, session: dict):
        """保存账号到数据库"""
        try:
            async with AsyncSessionLocal() as db_session:
                repo = AccountRepository(db_session)
                
                # 检查是否已存在同平台账号
                existing = await repo.get_by_platform(session['platform'])
                
                user_name = session['user_name'] or f"{session['platform']}_{session['id'][:8]}"
                
                if existing:
                    # 更新现有账号
                    existing.account_name = user_name
                    existing.cookie_file = session['cookie_file']
                    existing.is_active = True
                    await db_session.commit()
                    session['account_id'] = existing.id
                else:
                    # 创建新账号
                    account = await repo.create(
                        platform=session['platform'],
                        account_name=user_name,
                        cookie_file=session['cookie_file'],
                    )
                    await db_session.commit()
                    session['account_id'] = account.id
                    
        except Exception as e:
            logger.error(f"Save account to DB failed: {e}")
    
    async def _navigate_to_creator_platform(self, session: dict):
        """导航到创作者平台"""
        try:
            page = session.get('page')
            creator_url = self.CREATOR_URLS.get(session['platform'])
            
            if creator_url and page and not page.is_closed():
                await page.goto(creator_url, wait_until="domcontentloaded")
                session['status'] = 'creator_platform'
                logger.info(f"Navigated to creator platform for session {session['id']}")
                
        except Exception as e:
            logger.error(f"Navigate to creator platform failed: {e}")
    
    async def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        async with self._lock:
            return await self._close_session_internal(session_id)
    
    async def _close_session_internal(self, session_id: str) -> bool:
        """内部关闭会话实现"""
        session = self.sessions.pop(session_id, None)
        if not session:
            return False
        
        logger.info(f"Closing interactive browser session {session_id}")
        
        session['status'] = 'closed'
        
        # 关闭页面
        try:
            page = session.get('page')
            if page and not page.is_closed():
                await page.close()
        except Exception:
            pass
        
        # 关闭上下文
        try:
            context = session.get('context')
            if context:
                await context.close()
        except Exception:
            pass
        
        # 关闭浏览器
        try:
            browser = session.get('browser')
            if browser:
                await browser.close()
        except Exception:
            pass
        
        # 停止 Playwright
        try:
            playwright = session.get('_playwright')
            if playwright:
                await playwright.stop()
        except Exception:
            pass
        
        return True
    
    async def _cleanup_loop(self):
        """定期清理超时会话"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次
                
                now = time.time()
                expired_sessions = []
                
                for session_id, session in self.sessions.items():
                    # 检查是否超过最大存活时间（30分钟）
                    if now - session['created_at'] > 1800:
                        expired_sessions.append(session_id)
                        continue
                    
                    # 检查浏览器是否已关闭
                    browser = session.get('browser')
                    if browser and not browser.is_connected():
                        expired_sessions.append(session_id)
                        continue
                    
                    # 检查页面是否已关闭
                    page = session.get('page')
                    if page and page.is_closed():
                        expired_sessions.append(session_id)
                
                for session_id in expired_sessions:
                    logger.info(f"Session {session_id} expired or closed, cleaning up")
                    await self.close_session(session_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """获取会话信息"""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        return {
            'sessionId': session['id'],
            'platform': session['platform'],
            'status': session['status'],
            'userName': session['user_name'],
            'accountId': session['account_id'],
            'error': session['error_msg'],
        }
    
    def update_heartbeat(self, session_id: str) -> bool:
        """更新会话心跳"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        session['last_heartbeat'] = time.time()
        return True
    
    def _should_use_headless(self) -> bool:
        """检测是否应该使用 headless 模式
        
        检测以下条件：
        1. 环境变量 INTERACTIVE_HEADLESS=true/false（最高优先级）
        2. macOS: 默认尝试非 headless（Playwright 原生支持）
        3. Linux: 检测 DISPLAY 和 X Server
        4. Windows: 默认尝试非 headless
        """
        import os
        import platform
        
        # 如果明确设置了环境变量，优先使用
        headless_env = os.environ.get('UPLOADER_HEADLESS', '').lower()
        if headless_env in ('true', '1', 'yes'):
            return True
        if headless_env in ('false', '0', 'no'):
            return False
        
        system = platform.system()
        
        # macOS: Playwright 原生支持，默认尝试弹窗
        if system == 'Darwin':
            return False
        
        # Windows: 默认尝试弹窗
        if system == 'Windows':
            return False
        
        # Linux: 检测 X Server
        # 检测 DISPLAY 环境变量
        display = os.environ.get('DISPLAY')
        if not display:
            # 没有 DISPLAY 变量，可能是 Docker/SSH 环境
            return True
        
        # 尝试检测 X Server 是否真的可用
        try:
            import subprocess
            result = subprocess.run(
                ['xdpyinfo'],
                capture_output=True,
                timeout=2
            )
            if result.returncode != 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            # xdpyinfo 不存在或执行失败，可能是无图形环境
            return True
        
        return False
    
    async def get_account_for_platform(self, platform: str) -> Optional[dict]:
        """获取平台的已登录账号"""
        try:
            async with AsyncSessionLocal() as db_session:
                repo = AccountRepository(db_session)
                account = await repo.get_by_platform(platform)
                if account:
                    return {
                        'id': account.id,
                        'platform': account.platform,
                        'user_name': account.account_name,
                        'cookie_file': account.cookie_file,
                    }
                return None
        except Exception as e:
            logger.error(f"Get account for platform failed: {e}")
            return None


# 快捷获取实例的方法
async def get_interactive_browser_manager() -> InteractiveBrowserManager:
    manager = await InteractiveBrowserManager.get_instance()
    await manager.start()
    return manager
