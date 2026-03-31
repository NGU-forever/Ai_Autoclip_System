# -*- coding: utf-8 -*-
"""
小红书扫码登录实现
"""

import asyncio
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Dict, Optional

from playwright.async_api import async_playwright

from src.config import settings
from uploader.conf import LOCAL_CHROME_PATH
from uploader.utils.base_social_media import set_init_script
from uploader.utils.playwright_net import (
    goto_with_retry,
    merge_chromium_launch_options,
    user_friendly_uploader_error,
    platform_label_for_error,
)

from .base import BasePlatformLogin
from .models import LoginStatus

logger = logging.getLogger(__name__)


class XHSLogin(BasePlatformLogin):
    """小红书扫码登录"""

    _XHS_LOGIN_PANEL_RECT_JS = """() => {
        const bodyText = document.body && document.body.innerText ? document.body.innerText : '';
        const looksLikePhoneOrSmsLogin =
            bodyText.includes('手机号登录')
            || bodyText.includes('短信登录')
            || (bodyText.includes('验证码')
                && (bodyText.includes('手机号') || bodyText.includes('+86')));
        if (!looksLikePhoneOrSmsLogin) {
            return null;
        }
        function panelMatchesLogin(text) {
            if (text.includes('手机号登录') || text.includes('短信登录')) return true;
            if (text.includes('验证码') && (text.includes('手机号') || text.includes('+86'))) {
                return true;
            }
            return false;
        }
        const candidates = document.querySelectorAll('div, section, form, aside, article');
        let best = null;
        let bestArea = 0;
        for (const el of candidates) {
            const r = el.getBoundingClientRect();
            if (r.width < 220 || r.height < 160 || r.width > 920 || r.height > 720) continue;
            if (r.top < 8 || r.left < 8) continue;
            const text = (el.innerText || '').slice(0, 800);
            if (!panelMatchesLogin(text)) continue;
            const area = r.width * r.height;
            if (area > bestArea) {
                bestArea = area;
                best = el;
            }
        }
        if (!best) return null;
        const r = best.getBoundingClientRect();
        return { x: r.left, y: r.top, width: r.width, height: r.height };
    }"""

    def __init__(self):
        super().__init__("xhs")

    async def login(self, task) -> None:
        """执行小红书登录流程"""
        logger.info(f"Starting XiaoHongShu login for task {task.id}")
        async with async_playwright() as playwright:
            launch_options = merge_chromium_launch_options({"headless": True})
            if LOCAL_CHROME_PATH:
                launch_options["executable_path"] = LOCAL_CHROME_PATH

            browser = await playwright.chromium.launch(**launch_options)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
            )
            context = await set_init_script(context)
            page = await context.new_page()

            try:
                logger.info("Navigating to https://creator.xiaohongshu.com/")
                await goto_with_retry(
                    page,
                    "https://creator.xiaohongshu.com/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                    retries=3,
                    delay_sec=2.5,
                    log_label=f"XHS QR task {task.id} goto",
                )
                await self._wait_xhs_login_ui(page)

                logger.info(f"Page loaded: {await page.title()} - {page.url}")

                await self._switch_xhs_to_scan_qr_mode(page)

                panel_rect = await self.get_xhs_login_panel_viewport_rect(page)
                ok = await self._capture_login_qr_fast(
                    page,
                    task.qr_code_path,
                    "XHS",
                    min_qr_area=120 * 120,
                    initial_sleep=0.2,
                    poll_interval=0.18,
                    pre_screenshot_sleep=0.06,
                    container_rect=panel_rect,
                )
                png_ok = (
                    ok
                    and os.path.exists(task.qr_code_path)
                    and os.path.getsize(task.qr_code_path) >= 200
                )
                if png_ok:
                    logger.info(f"Screenshot saved to {task.qr_code_path}")
                    task.qr_ready.set()
                else:
                    logger.error(f"Failed to generate valid QR PNG at {task.qr_code_path}")
                    task.status = LoginStatus.FAILED
                    task.error_msg = "二维码生成失败"
                    task.qr_ready.set()
                    return

                logger.info("QR code generated, waiting for scan...")

                # 开启扫码状态检测后台任务
                scan_detected = False

                async def _monitor_scan():
                    nonlocal scan_detected
                    for _ in range(150):
                        if scan_detected:
                            return
                        try:
                            page_text = await page.content()
                            if any(x in page_text for x in ['\u5df2\u626b\u7801', '\u626b\u63cf\u6210\u529f', '\u8bf7\u5728\u624b\u673a\u4e0a\u786e\u8ba4', '\u786e\u8ba4\u767b\u5f55']):
                                scan_detected = True
                                task.status = LoginStatus.SCANNING
                                logger.info("XHS QR code scanned, waiting for confirmation")
                                return
                        except Exception:
                            pass
                        await asyncio.sleep(2)

                scan_task = asyncio.create_task(_monitor_scan())
                try:
                    await page.wait_for_function(
                        """
                        () => {
                            const url = window.location.href;
                            return [
                                'creator.xiaohongshu.com/creator-micro',
                                'creator.xiaohongshu.com/publish',
                            ].some(p => url.includes(p));
                        }
                        """,
                        timeout=300_000,
                    )
                    current_url = page.url
                    logger.info(f"XHS login success detected, URL: {current_url}")

                    cookie_filename = f"{uuid.uuid4().hex}.json"
                    platform_cookies_path = Path(settings.get_platform_cookies_path("xhs"))
                    platform_cookies_path.mkdir(parents=True, exist_ok=True)
                    cookie_path = platform_cookies_path / cookie_filename
                    await context.storage_state(path=str(cookie_path))

                    try:
                        user_name = await page.evaluate("""
                            () => {
                                const selectors = ['.user-name', '.nickname', '[class*="userName"]', '[class*="nickName"]'];
                                for (const s of selectors) {
                                    const el = document.querySelector(s);
                                    if (el && el.textContent.trim()) return el.textContent.trim();
                                }
                                return null;
                            }
                        """)
                    except Exception:
                        user_name = None

                    task.status = LoginStatus.SUCCESS
                    task.cookie_file = cookie_filename
                    task.user_name = user_name or f"小红书账号_{task.id[:8]}"

                except Exception as e:
                    logger.warning(f"XHS login wait_for_function ended: {e}")
                    if task.status not in (LoginStatus.SUCCESS, LoginStatus.SCANNING):
                        task.status = LoginStatus.EXPIRED
                        task.error_msg = "登录超时，请重试"
                finally:
                    scan_task.cancel()
                    try:
                        await scan_task
                    except asyncio.CancelledError:
                        pass

            except Exception as e:
                logger.error(f"Error in XHS QR login: {str(e)}")
                task.status = LoginStatus.FAILED
                task.error_msg = user_friendly_uploader_error(
                    e, platform_label_for_error("xhs")
                )
                task.qr_ready.set()
            finally:
                await context.close()
                await browser.close()

    async def _wait_xhs_login_ui(self, page) -> None:
        """DOM 就绪后等待登录层出现，比 wait_until=networkidle 快得多。"""
        hint = (
            page.locator("text=短信登录")
            .or_(page.locator("text=手机号登录"))
            .or_(page.locator("text=验证码"))
            .first
        )
        try:
            await hint.wait_for(state="visible", timeout=12000)
        except Exception:
            logger.debug("XHS: login UI hint not visible in time, continuing")
            await asyncio.sleep(0.35)

    async def get_xhs_login_panel_viewport_rect(self, page) -> Optional[Dict]:
        """与扫码模式切换同源：定位短信/手机号登录弹层，用于限制二维码截取区域。"""
        try:
            raw = await page.evaluate(self._XHS_LOGIN_PANEL_RECT_JS)
        except Exception as e:
            logger.debug(f"XHS: login panel rect evaluate failed: {e}")
            return None
        if not raw or not isinstance(raw, dict):
            logger.debug("XHS: login panel rect not found (no matching panel)")
            return None
        try:
            return {
                "x": float(raw["x"]),
                "y": float(raw["y"]),
                "width": float(raw["width"]),
                "height": float(raw["height"]),
            }
        except (KeyError, TypeError, ValueError):
            logger.debug("XHS: login panel rect malformed: %s", raw)
            return None

    async def _switch_xhs_to_scan_qr_mode(self, page) -> None:
        """
        小红书默认常为手机号/短信验证码登录；需点击登录框右上角折角才会出现可扫码的登录二维码。
        改版后标题多为「短信登录」而非「手机号登录」，检测需覆盖两种文案。
        顺序：登录层右上角 elementFromPoint → 语义选择器 → 原有文案/类名按钮。
        """
        await asyncio.sleep(0.12)

        corner_result = None
        corner_mouse_xy = None
        try:
            corner_payload = await page.evaluate(
                """() => {
                    const bodyText = document.body && document.body.innerText ? document.body.innerText : '';
                    const looksLikePhoneOrSmsLogin =
                        bodyText.includes('手机号登录')
                        || bodyText.includes('短信登录')
                        || (bodyText.includes('验证码')
                            && (bodyText.includes('手机号') || bodyText.includes('+86')));
                    if (!looksLikePhoneOrSmsLogin) {
                        return { status: 'no_phone_ui' };
                    }
                    function panelMatchesLogin(text) {
                        if (text.includes('手机号登录') || text.includes('短信登录')) return true;
                        if (text.includes('验证码') && (text.includes('手机号') || text.includes('+86'))) {
                            return true;
                        }
                        return false;
                    }
                    const candidates = document.querySelectorAll('div, section, form, aside, article');
                    let best = null;
                    let bestArea = 0;
                    for (const el of candidates) {
                        const r = el.getBoundingClientRect();
                        if (r.width < 220 || r.height < 160 || r.width > 920 || r.height > 720) continue;
                        if (r.top < 8 || r.left < 8) continue;
                        const text = (el.innerText || '').slice(0, 800);
                        if (!panelMatchesLogin(text)) continue;
                        const area = r.width * r.height;
                        if (area > bestArea) {
                            bestArea = area;
                            best = el;
                        }
                    }
                    if (!best) return { status: 'no_modal' };
                    const r = best.getBoundingClientRect();
                    const cornerX = r.right - 28;
                    const cornerY = r.top + 28;
                    for (const o of [28, 22, 36, 18, 44, 52, 16]) {
                        const x = r.right - o;
                        const y = r.top + o;
                        if (x < 4 || y < 4 || x > window.innerWidth - 4 || y > window.innerHeight - 4) continue;
                        const hit = document.elementFromPoint(x, y);
                        if (hit && hit !== document.body && hit !== document.documentElement) {
                            hit.click();
                            return { status: 'clicked_corner' };
                        }
                    }
                    return { status: 'corner_miss', x: cornerX, y: cornerY };
                }"""
            )
            if isinstance(corner_payload, dict):
                corner_result = corner_payload.get("status")
                if corner_payload.get("x") is not None and corner_payload.get("y") is not None:
                    corner_mouse_xy = (
                        float(corner_payload["x"]),
                        float(corner_payload["y"]),
                    )
            else:
                corner_result = corner_payload

            if corner_result == "clicked_corner":
                logger.info("XHS QR mode: clicked login panel top-right (corner toggle)")
                await asyncio.sleep(0.45)
            elif corner_result == "corner_miss" and corner_mouse_xy:
                try:
                    await page.mouse.click(corner_mouse_xy[0], corner_mouse_xy[1])
                    logger.info(
                        "XHS QR mode: mouse.click login corner (DOM click missed) at (%.0f, %.0f)",
                        corner_mouse_xy[0],
                        corner_mouse_xy[1],
                    )
                    await asyncio.sleep(0.45)
                    corner_result = "clicked_corner"
                except Exception as e:
                    logger.debug(f"XHS corner mouse.click failed: {e}")
            else:
                logger.debug(f"XHS QR mode corner attempt: {corner_result}")
        except Exception as e:
            logger.debug(f"XHS corner toggle evaluate failed: {e}")

        corner_clicked = corner_result == "clicked_corner"
        if not corner_clicked:
            for name_pattern in (
                re.compile(r"扫码"),
                re.compile(r"二维码"),
            ):
                try:
                    tab = page.get_by_role("tab", name=name_pattern)
                    if await tab.count() > 0:
                        await tab.first.click(timeout=2000)
                        logger.info(
                            "XHS QR mode: clicked role=tab matching %s", name_pattern.pattern
                        )
                        await asyncio.sleep(0.4)
                        break
                except Exception as e:
                    logger.debug(f"XHS tab click: {e}")

            for sel in (
                '[aria-label*="二维码"]',
                '[aria-label*="扫码"]',
                '[title*="二维码"]',
                '[title*="扫码"]',
            ):
                try:
                    loc = page.locator(sel).first
                    await loc.wait_for(state="visible", timeout=1500)
                    await loc.click(timeout=1500)
                    logger.info(f"XHS QR mode: clicked {sel}")
                    await asyncio.sleep(0.4)
                    break
                except Exception as e:
                    logger.debug(f"XHS selector {sel}: {e}")

        scan_login_selectors = [
            "text='扫码登录'",
            "text='二维码登录'",
            "button:has-text('扫码')",
            "button:has-text('二维码')",
            "[class*='scan']",
            "[class*='qrcode']",
        ]
        for selector in scan_login_selectors:
            try:
                btn = await page.wait_for_selector(selector, timeout=1800)
                if btn:
                    await btn.click()
                    logger.info(f"XHS QR mode: clicked scan helper {selector}")
                    await asyncio.sleep(0.45)
                    break
            except Exception:
                continue
