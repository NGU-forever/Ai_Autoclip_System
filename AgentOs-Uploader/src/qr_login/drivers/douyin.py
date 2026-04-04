# -*- coding: utf-8 -*-
"""
抖音 QR Driver

职责：抖音平台特定的 DOM 操作
- 点击扫码登录 tab
- 捕获抖音二维码（处理作品体裁轮播干扰）
- 检测扫码状态
"""

import asyncio
import logging
import math
import os
import re
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import Page

from .base import BaseQRDriver

logger = logging.getLogger(__name__)


class DouyinDriver(BaseQRDriver):
    """抖音 QR Driver - 纯 DOM 操作"""
    
    def __init__(self):
        super().__init__("douyin")
    
    async def prepare_login_page(self, page: Page) -> None:
        """准备抖音登录页面
        
        抖音创作者登录弹层常混入「作品体裁」等运营轮播，
        需要尝试切到扫码 Tab、点文案或「刷新二维码」以露出真实登录码区域。
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
    
    async def capture_qr_code(self, page: Page, output_path: str) -> bool:
        """捕获抖音二维码
        
        抖音专用：不用通用「最大面积方形图」策略，
        改为 prime + 中心带 canvas 优先 + 排除运营文案祖先。
        """
        min_png = 200
        max_attempts = 82
        poll_interval = 0.48

        await self.prepare_login_page(page)
        await asyncio.sleep(1.0)

        for attempt in range(max_attempts):
            if attempt > 0 and attempt % 16 == 0:
                await self.prepare_login_page(page)
                await asyncio.sleep(0.85)

            el, area, kind = await self._pick_login_qr_candidate(page)
            if el is not None and area >= 168 * 168:
                try:
                    await asyncio.sleep(0.26)
                    await el.screenshot(path=output_path)
                    if os.path.exists(output_path) and os.path.getsize(output_path) >= min_png:
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

        # Fallback: 中心裁剪截图
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
            await page.screenshot(path=output_path, clip=clip)
            if os.path.exists(output_path) and os.path.getsize(output_path) >= min_png:
                return True
        except Exception as e:
            logger.debug("Douyin QR fallback clip failed: %s", e)

        return False
    
    async def detect_scan_status(self, page: Page) -> str:
        """检测抖音扫码状态"""
        try:
            page_text = await page.content()
            
            # 检测已扫码
            scan_indicators = ['已扫码', '扫描成功', '请在手机上确认', '确认登录']
            if any(x in page_text for x in scan_indicators):
                return 'scanning'
            
            # 检测过期
            expired_indicators = ['二维码已过期', '二维码已失效', '请刷新']
            if any(x in page_text for x in expired_indicators):
                return 'expired'
            
            # 检测成功（通过 URL，Manager 层会二次确认）
            url = page.url.lower()
            if 'creator-micro/content/upload' in url or 'creator.douyin.com/creator-micro' in url:
                return 'success'
            
            return 'pending'
        except Exception as e:
            logger.debug(f"Douyin detect scan status error: {e}")
            return 'unknown'
    
    async def get_user_name(self, page: Page) -> Optional[str]:
        """获取抖音用户名"""
        try:
            # 等待用户信息加载（侧边栏或顶部通常有用户名称）
            try:
                await page.wait_for_selector('.user-name, .nickname, [class*="userName"], [class*="user-name"]', timeout=5000)
            except:
                pass

            user_name = await page.evaluate("""
                () => {
                    const selectors = [
                        '.user-name', '.nickname', '[class*="userName"]', '[class*="user-name"]',
                        '[data-e2e="user-name"]', '.user-info-name'
                    ];
                    for (const s of selectors) {
                        const el = document.querySelector(s);
                        if (el && el.textContent.trim()) return el.textContent.trim();
                    }
                    return null;
                }
            """)
            return user_name
        except Exception as e:
            logger.debug(f"Douyin get user name error: {e}")
            return None
    
    async def refresh_qr_code(self, page: Page) -> bool:
        """刷新抖音二维码"""
        try:
            btn = page.get_by_role("button", name=re.compile(r"刷新.*二维码|重新获取"))
            if await btn.count() > 0 and await btn.first.is_visible():
                await btn.first.click(timeout=3000)
                return True
        except Exception as e:
            logger.debug(f"Douyin refresh QR failed: {e}")
        return False
    
    # ─────────────────────────────────────────────────────────────────
    # 内部辅助方法
    # ─────────────────────────────────────────────────────────────────
    
    async def _element_in_promo_carousel(self, handle: Any) -> bool:
        """是否在「作品体裁」运营小块内"""
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
    
    def _is_squareish_qr_box(self, w: float, h: float) -> bool:
        """登录二维码多为正方形，过滤长条 banner / 图标"""
        if w < 56 or h < 56:
            return False
        if w > 520 or h > 520:
            return False
        ratio = w / h if h else 0.0
        return 0.82 <= ratio <= 1.22
    
    async def _pick_login_qr_candidate(
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
                        if await self._element_in_promo_carousel(h):
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
