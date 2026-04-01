# -*- coding: utf-8 -*-
"""
视频号（腾讯）QR Driver

职责：视频号平台特定的 DOM 操作
- 捕获视频号二维码
- 检测扫码状态
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import Page

from .base import BaseQRDriver

logger = logging.getLogger(__name__)


class TencentDriver(BaseQRDriver):
    """视频号 QR Driver - 纯 DOM 操作"""
    
    def __init__(self):
        super().__init__("tencent")
    
    async def prepare_login_page(self, page: Page) -> None:
        """准备视频号登录页面
        
        视频号直接进入登录页，不需要额外准备操作。
        只需等待二维码元素出现。
        """
        try:
            # 等待登录弹层/二维码元素出现
            await page.wait_for_selector(
                "canvas, img[src*='qr'], .wx-login-qrcode",
                state="visible",
                timeout=10000,
            )
        except Exception:
            pass  # 元素未出现也继续截图逻辑
    
    async def capture_qr_code(self, page: Page, output_path: str) -> bool:
        """捕获视频号二维码
        
        使用通用的二维码检测逻辑：
        - 在主页面和所有 iframe 中查找最像二维码的 canvas/img
        - 优先选择视口中部的正方形元素
        """
        min_png = 200
        min_qr_area = 56 * 56
        initial_sleep = 0.6
        poll_interval = 0.35
        pre_screenshot_sleep = 0.12
        max_attempts = 50

        await asyncio.sleep(initial_sleep)

        for attempt in range(max_attempts):
            el, area, kind = await self._pick_best_qr_element(page, min_area=min_qr_area)
            if el is not None and area >= min_qr_area:
                try:
                    await asyncio.sleep(pre_screenshot_sleep)
                    await el.screenshot(path=output_path)
                    if os.path.exists(output_path) and os.path.getsize(output_path) >= min_png:
                        logger.info(
                            f"Tencent QR captured ({kind}, area≈{area:.0f}), attempt={attempt + 1}"
                        )
                        return True
                except Exception as e:
                    logger.debug(f"Tencent QR screenshot failed: {e}")

            if attempt == 0 or (attempt + 1) % 12 == 0:
                logger.info(
                    f"Tencent QR polling canvas/img (attempt {attempt + 1}/{max_attempts})"
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
                logger.warning(f"Tencent QR fallback viewport clip ({name})")
                await page.screenshot(path=output_path, clip=clip)
                if os.path.exists(output_path) and os.path.getsize(output_path) >= min_png:
                    return True
            except Exception as e:
                logger.debug(f"Tencent fallback clip {name} failed: {e}")

        return False
    
    async def detect_scan_status(self, page: Page) -> str:
        """检测视频号扫码状态"""
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
            if 'channels.weixin.qq.com/platform' in url or '#/platform' in url:
                return 'success'
            
            return 'pending'
        except Exception as e:
            logger.debug(f"Tencent detect scan status error: {e}")
            return 'unknown'
    
    async def get_user_name(self, page: Page) -> Optional[str]:
        """获取视频号用户名
        
        视频号的用户名获取比较困难，通常需要进入创作者中心后才能获取。
        这里返回 None，由 Manager 层使用默认名称。
        """
        # 视频号用户名获取较复杂，暂返回 None
        return None
    
    # ─────────────────────────────────────────────────────────────────
    # 内部辅助方法
    # ─────────────────────────────────────────────────────────────────
    
    def _is_squareish_qr_box(self, w: float, h: float) -> bool:
        """登录二维码多为正方形"""
        if w < 56 or h < 56:
            return False
        if w > 520 or h > 520:
            return False
        ratio = w / h if h else 0.0
        return 0.82 <= ratio <= 1.22
    
    async def _pick_best_qr_element(
        self,
        page: Page,
        min_area: float = 0.0,
    ) -> Tuple[Optional[Any], float, str]:
        """
        在主页面与所有 iframe 中查找最像二维码的节点（canvas 或 img）。
        微信页面常在 iframe 内绘码，仅查 main frame 会漏掉 canvas。
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
                    collected.append((h, area, "canvas", w, hgt))
            except Exception as e:
                logger.debug(f"Tencent frame canvas scan: {e}")

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
                    collected.append((h, area, "img", w, hgt))
            except Exception as e:
                logger.debug(f"Tencent frame img scan: {e}")

        if not collected:
            return None, 0.0, ""
        
        # 选择面积最大的
        best = max(collected, key=lambda c: c[1])
        return best[0], best[1], best[2]
