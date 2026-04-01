# -*- coding: utf-8 -*-
"""
统一登录成功判定工具

整合各平台验证后的判定逻辑，提供可靠的登录成功检测。
整合了 URL、Cookie、DOM 元素和页面标题的多重检测与置信度评分系统。
"""

import logging
import time
from typing import Dict, List, Set, Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class LoginSuccessDetector:
    """登录成功检测器 (增强版)
    
    使用多种检测方式提高准确性：URL 匹配、DOM 元素检测、Cookie 检测、标题检测。
    """
    
    # 硬编码 URL 模式（明确指示登录成功）
    URL_PATTERNS: Dict[str, List[str]] = {
        "douyin": [
            "creator-micro/content/upload",
            "creator.douyin.com/creator-micro",
            "creator.douyin.com/home",
            "creator.douyin.com/dashboard",
        ],
        "tencent": [
            "channels.weixin.qq.com/platform",
            "#/platform",
            "#/creator",
            "platform/post/create",
            "platform/post/list",
        ],
        "xhs": [
            "creator.xiaohongshu.com/creator-micro",
            "creator.xiaohongshu.com/publish",
        ],
    }
    
    # 关键 Cookie 名称
    COOKIE_NAMES: Dict[str, List[str]] = {
        "douyin": ["sessionid", "sid_guard", "sid_tt", "uid_tt"],
        "tencent": ["wxtokenkey", "wxuin", "wxsid"],
        "xhs": ["web_session", "userId"],
    }

    # 关键 DOM 选择器 (用于确认已进入后台界面)
    DOM_SELECTORS: Dict[str, List[str]] = {
        "douyin": [
            ".upload-video-container",
            ".creator-home-header",
            "text='发布视频'",
            "text='首页'",
            ".account-info-container",
        ],
        "tencent": [
            ".channels-platform-layout",
            ".header-user-info",
            "text='发表视频'",
            "text='主页'",
            ".platform-header-v2",
        ],
        "xhs": [
            ".publish-container",
            ".creator-header",
            "text='发布笔记'",
            "text='数据中心'",
            ".user-info-container",
        ],
    }

    # 页面标题指示语
    TITLE_INDICATORS: Dict[str, List[str]] = {
        "douyin": ["创作者", "抖音", "创作服务平台"],
        "tencent": ["视频号", "创作者", "微信"],
        "xhs": ["小红书", "创作", "创作者中心"],
    }
    
    @classmethod
    async def check(cls, page: Page, platform: str) -> bool:
        """检测是否登录成功 (置信度评分版)"""
        if not page:
            return False
            
        current_url = page.url
        
        # 0. 基础判定：是否仍在登录页/通行证页？
        is_login_page = cls._is_at_login_page(platform, current_url)
        
        score = 0
        detected_methods = []
        
        # 1. URL 检测
        if cls._check_url(page, platform) and not is_login_page:
            score += 2
            detected_methods.append("url")
        
        # 2. DOM 元素检测
        if await cls._check_dom(page, platform):
            score += 3
            detected_methods.append("dom")
        
        # 3. Cookie 检测
        cookie_matched = await cls._check_cookies(page, platform)
        if cookie_matched:
            score += 2
            detected_methods.append("cookie")
            
        # 4. 标题检测
        if await cls._check_title(page, platform):
            score += 1
            detected_methods.append("title")

        # 综合判定逻辑
        is_logged_in = (
            score >= 3
            or ("dom" in detected_methods and len(detected_methods) >= 2)
            or ("cookie" in detected_methods and "url" in detected_methods)
            or (cookie_matched and not is_login_page)
        )
        
        if is_logged_in:
            logger.info(
                f"[{platform}] ✅ Login success confirmed (score={score}, methods={detected_methods}, url={current_url[:80]})"
            )
        elif score > 0:
            # 有部分信号但未达阈值，记录详细信息帮助诊断
            logger.debug(
                f"[{platform}] Partial signals (score={score}, methods={detected_methods}, "
                f"is_login_page={is_login_page}, url={current_url[:80]})"
            )
            
        return is_logged_in
    
    @classmethod
    def _is_at_login_page(cls, platform: str, url: str) -> bool:
        """判断当前页面是否明确属于登录流程中"""
        ul = url.lower()
        if platform == "tencent" and "channels.weixin.qq.com/login.html" in ul:
            frag = (url.split("#", 1)[-1] if "#" in url else "").lower()
            return not ("platform" in frag or "post" in frag)
        
        if any(x in ul for x in ("passport", "qrconnect", "open.weixin.qq.com", "open.weixin", "signin")):
            return True
            
        if "login" in ul and not any(
            h in ul for h in ("#/platform", "#/creator", "creator-micro/content/upload")
        ):
            return True
            
        return False

    @classmethod
    def _check_url(cls, page: Page, platform: str) -> bool:
        """通过 URL 检测登录成功"""
        url = page.url.lower()
        patterns = cls.URL_PATTERNS.get(platform, [])
        return any(pattern.lower() in url for pattern in patterns)
    
    @classmethod
    async def _check_dom(cls, page: Page, platform: str) -> bool:
        """通过 DOM 检测登录成功"""
        selectors = cls.DOM_SELECTORS.get(platform, [])
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    txt = await el.text_content()
                    if txt and len(txt.strip()) > 0:
                        return True
            except Exception:
                continue
        return False

    @classmethod
    async def _check_cookies(cls, page: Page, platform: str) -> bool:
        """通过 Cookie 检测登录成功"""
        try:
            cookies = await page.context.cookies()
            cookie_dict = {c["name"]: c for c in cookies}
            required = cls.COOKIE_NAMES.get(platform, [])
            
            for name in required:
                cookie = cookie_dict.get(name)
                if cookie and cookie.get("value") and len(cookie["value"]) > 5:
                    exp = cookie.get("expires", -1)
                    if exp == -1 or exp > time.time():
                        return True
            return False
        except Exception:
            return False
            
    @classmethod
    async def _check_title(cls, page: Page, platform: str) -> bool:
        """通过标题检测登录成功"""
        try:
            title = await page.title()
            keywords = cls.TITLE_INDICATORS.get(platform, [])
            if any(kw in title for kw in keywords):
                if not any(word in title for word in ["登录", "扫码", "Login", "Sign"]):
                    return True
        except Exception:
            pass
        return False


async def is_logged_in(page: Page, platform: str) -> bool:
    """便捷函数：检测是否已登录"""
    return await LoginSuccessDetector.check(page, platform)
