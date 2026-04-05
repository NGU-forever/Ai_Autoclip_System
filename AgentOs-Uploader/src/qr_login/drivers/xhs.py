# -*- coding: utf-8 -*-
"""
小红书 QR Driver

职责：小红书平台特定的 DOM 操作
- 切换到扫码登录模式
- 捕获小红书二维码
- 检测扫码状态
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import Page

from .base import BaseQRDriver

logger = logging.getLogger(__name__)


class XHSDriver(BaseQRDriver):
    """小红书 QR Driver - 纯 DOM 操作"""
    
    def __init__(self):
        super().__init__("xhs")
    
    async def prepare_login_page(self, page: Page) -> None:
        """准备小红书登录页面
        
        小红书默认显示手机号登录，需要点击切换到扫码模式。
        """
        await self._wait_login_ui(page)
        await self._switch_to_scan_qr_mode(page)
    
    async def capture_qr_code(self, page: Page, output_path: str) -> bool:
        """捕获小红书二维码
        
        小红书二维码在登录弹层内，需要限制在弹层区域内检测。
        """
        min_png = 200
        min_qr_area = 120 * 120
        initial_sleep = 0.2
        poll_interval = 0.18
        pre_screenshot_sleep = 0.06
        max_attempts = 50

        await asyncio.sleep(initial_sleep)
        
        # 获取登录弹层区域
        panel_rect = await self._get_login_panel_rect(page)

        for attempt in range(max_attempts):
            el, area, kind = await self._pick_qr_in_container(
                page, min_area=min_qr_area, container_rect=panel_rect
            )
            if el is not None and area >= min_qr_area:
                try:
                    await asyncio.sleep(pre_screenshot_sleep)
                    await el.screenshot(path=output_path)
                    if os.path.exists(output_path) and os.path.getsize(output_path) >= min_png:
                        logger.info(
                            f"XHS QR captured ({kind}, area≈{area:.0f}), attempt={attempt + 1}"
                        )
                        return True
                except Exception as e:
                    logger.debug(f"XHS QR screenshot failed: {e}")

            if attempt == 0 or (attempt + 1) % 12 == 0:
                logger.info(
                    f"XHS QR polling canvas/img (attempt {attempt + 1}/{max_attempts})"
                )

            await asyncio.sleep(poll_interval)

        # Fallback: 视口裁剪
        vp = page.viewport_size or {"width": 1280, "height": 800}
        vw, vh = float(vp["width"]), float(vp["height"])
        fallback_clips = [
            ("right", vw * 0.50, vh * 0.12, min(400.0, vw * 0.46), min(440.0, vh * 0.76)),
            ("center", max(0.0, (vw - 360) / 2), max(0.0, (vh - 360) / 2), 360.0, 360.0),
        ]
        for name, x, y, cw, ch in fallback_clips:
            try:
                clip = {
                    "x": max(0.0, x),
                    "y": max(0.0, y),
                    "width": min(cw, vw - max(0.0, x)),
                    "height": min(ch, vh - max(0.0, y)),
                }
                if clip["width"] < 120 or clip["height"] < 120:
                    continue
                logger.warning(f"XHS QR fallback viewport clip ({name})")
                await page.screenshot(path=output_path, clip=clip)
                if os.path.exists(output_path) and os.path.getsize(output_path) >= min_png:
                    return True
            except Exception as e:
                logger.debug(f"XHS fallback clip {name} failed: {e}")

        return False
    
    async def detect_scan_status(self, page: Page) -> str:
        """检测小红书扫码状态"""
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
            
            # 检测成功（通过 URL）
            url = page.url.lower()
            if 'creator-micro/content/upload' in url or 'creator.xiaohongshu.com/publish' in url:
                return 'success'
            
            return 'pending'
        except Exception as e:
            logger.debug(f"XHS detect scan status error: {e}")
            return 'unknown'
    
    async def get_user_name(self, page: Page) -> Optional[str]:
        """获取小红书用户名"""
        try:
            user_name = await page.evaluate("""
                () => {
                    const selectors = [
                        '.creator-info [class*="name"]', '.ant-avatar + [class*="name"]',
                        '[data-testid="user-name"]', '.user-profile [class*="name"]',
                        '.user-name', '.nickname', '[class*="user"]', '[class*="name"]'
                    ];
                    for (const s of selectors) {
                        const el = document.querySelector(s);
                        if (el && el.textContent.trim()) {
                            // Clean up common suffixes/prefixes
                            let text = el.textContent.trim();
                            text = text.replace(/退出登录|logout|sign.*out/i, '').trim();
                            if (text) return text;
                        }
                    }
                    return null;
                }
            """)
            return user_name
        except Exception as e:
            logger.debug(f"XHS get user name error: {e}")
            return None
    
    # ─────────────────────────────────────────────────────────────────
    # 内部辅助方法
    # ─────────────────────────────────────────────────────────────────
    
    async def _wait_login_ui(self, page: Page) -> None:
        """等待登录 UI 出现"""
        try:
            await page.wait_for_selector(
                "text=手机号登录, text=短信登录, text=验证码",
                state="visible",
                timeout=15000,
            )
        except Exception:
            pass
    
    async def _switch_to_scan_qr_mode(self, page: Page) -> None:
        """切换到扫码登录模式"""
        try:
            success = await page.evaluate("""() => {
                const imgs = Array.from(document.querySelectorAll('img'));
                for (const img of imgs) {
                    if (img.src && img.src.includes('data:image/png')) {
                        const rect = img.getBoundingClientRect();
                        // 切换按钮通常较小 (64x64), 二维码通常较大 (160x160+)
                        if (rect.width > 0 && rect.width < 100) {
                            img.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if success:
                logger.info("XHS switched to QR mode via evaluated click")
                await asyncio.sleep(0.5)
                return
        except Exception as e:
            logger.debug(f"XHS QR evaluate click failed: {e}")

        # Fallback 1: 尝试点击扫码登录 tab
        try:
            qr_tab = page.get_by_text("扫码登录", exact=False)
            if await qr_tab.count() > 0:
                await qr_tab.first.click(timeout=3000)
                await asyncio.sleep(0.5)
                return
        except Exception:
            pass
        
        # Fallback 2: 尝试找二维码图标
        try:
            qr_icon = page.locator("[class*='qr'], [class*='scan']").first
            if await qr_icon.is_visible(timeout=2000):
                await qr_icon.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass
    
    async def _get_login_panel_rect(self, page: Page) -> Optional[Dict[str, float]]:
        """获取登录弹层区域"""
        js = """() => {
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
        
        try:
            return await page.evaluate(js)
        except Exception:
            return None
    
    def _is_squareish_qr_box(self, w: float, h: float) -> bool:
        """登录二维码多为正方形"""
        if w < 56 or h < 56:
            return False
        if w > 520 or h > 520:
            return False
        ratio = w / h if h else 0.0
        return 0.82 <= ratio <= 1.22
    
    def _qr_center_in_container(
        self, box: Dict[str, float], container_rect: Dict[str, float], margin: float = 10.0
    ) -> bool:
        cx = box["x"] + box["width"] / 2.0
        cy = box["y"] + box["height"] / 2.0
        l = container_rect["x"] - margin
        t = container_rect["y"] - margin
        r = container_rect["x"] + container_rect["width"] + margin
        b = container_rect["y"] + container_rect["height"] + margin
        return l <= cx <= r and t <= cy <= b
    
    async def _pick_qr_in_container(
        self,
        page: Page,
        min_area: float = 0.0,
        container_rect: Optional[Dict[str, float]] = None,
    ) -> Tuple[Optional[Any], float, str]:
        """
        在登录弹层内查找二维码元素。
        """
        collected: List[Tuple[Any, float, str, float, float]] = []

        for frame in page.frames:
            try:
                handles = await frame.query_selector_all("canvas")
                for h in handles:
                    box = await h.bounding_box()
                    if not box:
                        continue
                    w, hgt = box["width"], box["height"]
                    if not self._is_squareish_qr_box(w, hgt):
                        continue
                    area = w * hgt
                    if area < min_area:
                        continue
                    if container_rect and not self._qr_center_in_container(box, container_rect):
                        continue
                    collected.append((h, area, "canvas", w, hgt))
            except Exception as e:
                logger.debug(f"XHS frame canvas scan: {e}")

            try:
                for h in await frame.query_selector_all("img"):
                    box = await h.bounding_box()
                    if not box:
                        continue
                    w, hgt = box["width"], box["height"]
                    if not self._is_squareish_qr_box(w, hgt):
                        continue
                    area = w * hgt
                    if area < min_area:
                        continue
                    if container_rect and not self._qr_center_in_container(box, container_rect):
                        continue
                    collected.append((h, area, "img", w, hgt))
            except Exception as e:
                logger.debug(f"XHS frame img scan: {e}")

        if container_rect is not None and not collected:
            logger.debug("XHS: No QR candidates inside login panel rect, falling back to full-page pick")
            return await self._pick_qr_in_container(page, min_area=min_area, container_rect=None)

        if not collected:
            return None, 0.0, ""
        
        # 选择面积最大的
        best = max(collected, key=lambda c: c[1])
        return best[0], best[1], best[2]
