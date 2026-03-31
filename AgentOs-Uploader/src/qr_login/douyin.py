# -*- coding: utf-8 -*-
"""
抖音扫码登录实现
"""

import asyncio
import logging
import math
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import async_playwright, Page

from src.config import settings
from uploader.conf import LOCAL_CHROME_PATH
from uploader.utils.base_social_media import set_init_script
from uploader.utils.douyin_speed_routes import attach_douyin_speed_routes
from uploader.utils.playwright_net import (
    goto_with_retry,
    user_friendly_uploader_error,
    platform_label_for_error,
)

from .base import BasePlatformLogin
from .models import LoginStatus

logger = logging.getLogger(__name__)


class DouyinLogin(BasePlatformLogin):
    """抖音扫码登录"""

    def __init__(self):
        super().__init__("douyin")

    async def login(self, task) -> None:
        """执行抖音登录流程"""
        logger.info(f"Starting Douyin login for task {task.id}")
        async with async_playwright() as playwright:
            launch_options = self._get_launch_options()
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
            await attach_douyin_speed_routes(context)
            page = await context.new_page()

            try:
                logger.info("Navigating to https://creator.douyin.com/")
                await goto_with_retry(
                    page,
                    "https://creator.douyin.com/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                    retries=3,
                    delay_sec=2.5,
                    log_label=f"Douyin QR task {task.id} goto",
                )
                # 等待登录弹层出现（canvas 或登录相关文案），替代固定 sleep(2.8)
                try:
                    await page.wait_for_selector(
                        "canvas, text=扫码登录, text=二维码",
                        state="visible",
                        timeout=15000,
                    )
                except Exception:
                    pass  # 如果元素未出现，继续⎳图逻辑（_prime 会尝试切换模式）

                logger.info(f"Page loaded: {await page.title()} - {page.url}")

                ok = await self._capture_douyin_login_qr(page, task.qr_code_path)
                png_ok = (
                    ok
                    and os.path.exists(task.qr_code_path)
                    and os.path.getsize(task.qr_code_path) >= 200
                )
                if png_ok:
                    logger.info(f"Screenshot saved to {task.qr_code_path}")
                    task.qr_ready.set()
                else:
                    logger.error(f"Failed to generate QR code file at {task.qr_code_path}")
                    task.status = LoginStatus.FAILED
                    task.error_msg = "二维码生成失败"
                    task.qr_ready.set()
                    return

                logger.info("QR code generated, waiting for scan...")

                # 使用 wait_for_url 等待登录成功，同时开启扫码状态检测任务
                login_url_patterns = [
                    "creator-micro/content/upload",
                    "creator.douyin.com/creator-micro",
                    "creator.douyin.com/home",
                    "creator.douyin.com/dashboard",
                ]

                # 开启扫码检测后台任务
                scan_detected = False

                async def _monitor_scan():
                    nonlocal scan_detected
                    for _ in range(300):
                        if scan_detected or task.status not in (
                            LoginStatus.PENDING, LoginStatus.READY
                        ):
                            return
                        try:
                            page_text = await page.content()
                            if any(x in page_text for x in ['\u5df2\u626b\u7801', '\u626b\u63cf\u6210\u529f', '\u8bf7\u5728\u624b\u673a\u4e0a\u786e\u8ba4', '\u786e\u8ba4\u767b\u5f55']):
                                scan_detected = True
                                task.status = LoginStatus.SCANNING
                                logger.info("Douyin QR code scanned, waiting for confirmation")
                                return
                        except Exception:
                            pass
                        await asyncio.sleep(2)

                scan_task = asyncio.create_task(_monitor_scan())
                try:
                    # 等待登录成功 URL（最多 5 分钟）
                    await page.wait_for_function(
                        """
                        () => {
                            const url = window.location.href;
                            return [
                                'creator-micro/content/upload',
                                'creator.douyin.com/creator-micro',
                                'creator.douyin.com/home',
                                'creator.douyin.com/dashboard',
                            ].some(p => url.includes(p));
                        }
                        """,
                        timeout=300_000,
                    )
                    current_url = page.url
                    logger.info(f"Douyin login success detected, URL: {current_url}")

                    cookie_filename = f"{uuid.uuid4().hex}.json"
                    platform_cookies_path = Path(settings.get_platform_cookies_path("douyin"))
                    platform_cookies_path.mkdir(parents=True, exist_ok=True)
                    cookie_path = platform_cookies_path / cookie_filename
                    await context.storage_state(path=str(cookie_path))

                    try:
                        user_name = await page.evaluate("""
                            () => {
                                const selectors = ['.user-name', '.nickname', '[class*="userName"]', '[class*="user-name"]'];
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
                    task.user_name = user_name or f"抖音账号_{task.id[:8]}"

                except Exception as e:
                    logger.warning(f"Douyin login wait_for_function ended: {e}")
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
                logger.error(f"Error in Douyin QR login: {str(e)}")
                task.status = LoginStatus.FAILED
                task.error_msg = user_friendly_uploader_error(
                    e, platform_label_for_error("douyin")
                )
                task.qr_ready.set()
            finally:
                await context.close()
                await browser.close()

    def _get_launch_options(self) -> Dict:
        from uploader.utils.playwright_net import merge_chromium_launch_options
        return merge_chromium_launch_options({"headless": True})

    async def _prime_douyin_scan_login(self, page: Page) -> None:
        """
        抖音创作者登录弹层常混入「作品体裁」等运营轮播，与扫码区同屏。
        尝试切到扫码 Tab、点文案或「刷新二维码」以露出真实登录码区域。
        """
        # 1) 与验证码/密码并列的扫码 Tab
        for pattern in (r"扫码", r"二维码"):
            try:
                tab = page.get_by_role("tab", name=re.compile(pattern))
                if await tab.count() > 0:
                    t0 = tab.first
                    if await t0.is_visible():
                        await t0.click(timeout=2200)
                        await asyncio.sleep(0.55)
                        logger.info("Douyin prime: clicked tab matching %r", pattern)
                        break
            except Exception as e:
                logger.debug("Douyin prime tab %s: %s", pattern, e)

        # 2) 明确文案（部分改版无 role=tab）
        for text in ("扫码登录", "二维码登录"):
            try:
                loc = page.get_by_text(text, exact=True)
                if await loc.count() > 0:
                    el = loc.first
                    if await el.is_visible():
                        await el.click(timeout=2200)
                        await asyncio.sleep(0.45)
                        logger.info("Douyin prime: clicked text %r", text)
                        break
            except Exception as e:
                logger.debug("Douyin prime text %s: %s", text, e)

        # 3) 刷新二维码（轮播切页 / 重新拉取登录码）
        try:
            btn = page.get_by_role("button", name=re.compile(r"刷新.*二维码|重新获取|换.*二维码"))
            if await btn.count() > 0 and await btn.first.is_visible():
                await btn.first.click(timeout=2800)
                await asyncio.sleep(1.1)
                logger.info("Douyin prime: clicked refresh-QR button")
        except Exception as e:
            logger.debug("Douyin prime refresh button: %s", e)

    async def _douyin_element_in_promo_carousel(self, handle: Any) -> bool:
        """
        是否在「作品体裁」运营小块内。不能用整层弹层 innerText（会含全部子区），
        只认文案较短且同时带特征词的祖先，避免误伤中部真实登录 canvas。
        """
        try:
            return bool(
                await handle.evaluate(
                    """el => {
                      let n = el;
                      for (let i = 0; i < 6 && n; i++, n = n.parentElement) {
                        const t = (n.innerText || '');
                        if (t.length > 480) continue;
                        if (t.includes('作品体裁') && t.includes('发布视频')) return true;
                        if (t.includes('丰富的作品') && t.includes('发布图文')) return true;
                      }
                      return false;
                    }"""
                )
            )
        except Exception:
            return False

    async def _pick_douyin_login_qr_candidate(
        self, page: Page
    ) -> Tuple[Optional[Any], float, str]:
        """
        抖音专用：优先视口中部、边长约 168～288px 的正方形 canvas（登录码多为 canvas）；
        img 仅作备选且限制尺寸，并排除运营轮播祖先。
        """
        vp = page.viewport_size or {"width": 1280, "height": 800}
        vw, vh = float(vp["width"]), float(vp["height"])
        cx, cy = vw / 2.0, vh / 2.0
        max_dist = min(vw, vh) * 0.36
        min_side = 168.0
        max_side = 288.0

        def element_score(box: Dict[str, float], w: float, hgt: float, kind: str) -> float:
            if not self._is_squareish_qr_box(w, hgt):
                return -1.0
            side = min(w, hgt)
            if side < min_side or side > max_side:
                return -1.0
            mx = box["x"] + w / 2.0
            my = box["y"] + hgt / 2.0
            dist = math.hypot(mx - cx, my - cy)
            if dist > max_dist:
                return -1.0
            boost = 8000.0 if kind == "canvas" else 0.0
            return boost + side * side - dist * 2.8

        best_h: Any = None
        best_sc = -1.0
        best_area = 0.0
        best_kind = ""

        for frame in page.frames:
            for kind, sel in (("canvas", "canvas"), ("img", "img")):
                try:
                    handles = await frame.query_selector_all(sel)
                except Exception:
                    continue
                for h in handles:
                    try:
                        if await self._douyin_element_in_promo_carousel(h):
                            continue
                        box = await h.bounding_box()
                        if not box:
                            continue
                        w, hgt = box["width"], box["height"]
                        if kind == "img" and max(w, hgt) > 300:
                            continue
                        sc = element_score(box, w, hgt, kind)
                        if sc <= best_sc:
                            continue
                        best_sc = sc
                        best_h = h
                        best_area = w * hgt
                        best_kind = kind
                    except Exception:
                        continue

        return best_h, best_area, best_kind

    async def _capture_douyin_login_qr(self, page: Page, out_path: str) -> bool:
        """
        抖音：不用通用「最大面积方形图」策略，改为 prime + 中心带 canvas 优先 + 排除运营文案祖先。
        """
        min_png = 200
        max_attempts = 82
        poll_interval = 0.48

        await self._prime_douyin_scan_login(page)
        await asyncio.sleep(1.0)

        for attempt in range(max_attempts):
            if attempt > 0 and attempt % 16 == 0:
                await self._prime_douyin_scan_login(page)
                await asyncio.sleep(0.85)

            el, area, kind = await self._pick_douyin_login_qr_candidate(page)
            if el is not None and area >= 168 * 168:
                try:
                    await asyncio.sleep(0.26)
                    await el.screenshot(path=out_path)
                    if os.path.exists(out_path) and os.path.getsize(out_path) >= min_png:
                        logger.info(
                            "Douyin QR captured (%s, area≈%.0f), attempt=%s",
                            kind,
                            area,
                            attempt + 1,
                        )
                        return True
                except Exception as e:
                    logger.debug("Douyin QR screenshot failed: %s", e)

            if attempt == 0 or (attempt + 1) % 12 == 0:
                logger.info(
                    "Douyin QR dedicated poll (attempt %s/%s)",
                    attempt + 1,
                    max_attempts,
                )

            await asyncio.sleep(poll_interval)

        vp = page.viewport_size or {"width": 1280, "height": 800}
        vw, vh = float(vp["width"]), float(vp["height"])
        side = 260.0
        clip = {
            "x": max(0.0, (vw - side) / 2.0),
            "y": max(0.0, (vh - side) / 2.0 - 18.0),
            "width": min(side, vw),
            "height": min(side, vh),
        }
        try:
            logger.warning("Douyin QR: fallback center viewport clip")
            await page.screenshot(path=out_path, clip=clip)
            if os.path.exists(out_path) and os.path.getsize(out_path) >= min_png:
                return True
        except Exception as e:
            logger.debug("Douyin QR fallback clip failed: %s", e)

        return False
