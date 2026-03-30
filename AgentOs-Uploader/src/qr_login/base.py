# -*- coding: utf-8 -*-
"""
二维码登录基础类
包含共享的 QR 捕获工具和抽象基类
"""

import asyncio
import logging
import math
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class BasePlatformLogin(ABC):
    """平台登录基类"""

    def __init__(self, platform_name: str):
        self.platform_name = platform_name

    @abstractmethod
    async def login(self, task) -> None:
        """执行登录流程，子类必须实现"""
        pass

    def _is_squareish_qr_box(self, w: float, h: float) -> bool:
        """登录二维码多为正方形，过滤长条 banner / 图标。"""
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

    def _choose_from_qr_candidates(
        self,
        candidates: List[Tuple[Any, float, str, float, float]],
        *,
        refined_scoring: bool,
    ) -> Tuple[Optional[Any], float, str]:
        if not candidates:
            return None, 0.0, ""
        if not refined_scoring:
            best = max(candidates, key=lambda c: c[1])
            return best[0], best[1], best[2]

        max_area = max(c[1] for c in candidates)
        tier = [c for c in candidates if c[1] >= max_area * 0.85]
        pool = tier if tier else candidates

        def score_row(c: Tuple[Any, float, str, float, float]) -> Tuple[int, int, float]:
            _el, area, kind, w, hgt = c
            is_canvas = 1 if kind == "canvas" else 0
            side = min(w, hgt)
            typical = 1 if 160.0 <= side <= 320.0 else 0
            return (is_canvas, typical, area)

        best = max(pool, key=score_row)
        return best[0], best[1], best[2]

    async def _pick_best_qr_element(
        self,
        page: Page,
        min_area: float = 0.0,
        *,
        container_rect: Optional[Dict[str, float]] = None,
    ) -> Tuple[Optional[Any], float, str]:
        """
        在主页面与所有 iframe 中查找最像二维码的节点（canvas 或 img）。
        微信页面常在 iframe 内绘码，仅查 main frame 会漏掉 canvas。
        container_rect 为视口 CSS 像素矩形时，仅保留中心落在弹层内的候选，并优先 canvas 与典型边长。
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
                logger.debug(f"Frame canvas scan: {e}")

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
                logger.debug(f"Frame img scan: {e}")

        if container_rect is not None and not collected:
            logger.debug("No QR candidates inside login panel rect, falling back to full-page pick")
            return await self._pick_best_qr_element(page, min_area=min_area, container_rect=None)

        refined = container_rect is not None
        return self._choose_from_qr_candidates(collected, refined_scoring=refined)

    async def _capture_login_qr_fast(
        self,
        page: Page,
        out_path: str,
        label: str,
        min_qr_area: float = 56 * 56,
        *,
        initial_sleep: float = 0.6,
        poll_interval: float = 0.35,
        pre_screenshot_sleep: float = 0.12,
        max_attempts: int = 50,
        container_rect: Optional[Dict[str, float]] = None,
    ) -> bool:
        """
        通用：短间隔轮询主页面 + iframe，截最像二维码的 canvas/img；
        避免串行 wait_for_selector 各 5～6s；失败再右侧栏 + 居中裁剪。
        container_rect 可选，用于小红书等将候选限制在登录弹层内。
        """
        min_png = 200
        await asyncio.sleep(initial_sleep)

        for attempt in range(max_attempts):
            el, area, kind = await self._pick_best_qr_element(
                page, min_area=min_qr_area, container_rect=container_rect
            )
            if el is not None and area >= min_qr_area:
                try:
                    await asyncio.sleep(pre_screenshot_sleep)
                    await el.screenshot(path=out_path)
                    if os.path.exists(out_path) and os.path.getsize(out_path) >= min_png:
                        logger.info(
                            f"{label} QR captured ({kind}, area≈{area:.0f}), attempt={attempt + 1}"
                        )
                        return True
                except Exception as e:
                    logger.debug(f"Screenshot failed: {e}")

            if attempt == 0 or (attempt + 1) % 12 == 0:
                logger.info(
                    f"{label} QR polling canvas/img (attempt {attempt + 1}/{max_attempts})"
                )

            await asyncio.sleep(poll_interval)

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
                logger.warning(f"{label} QR fallback viewport clip ({name})")
                await page.screenshot(path=out_path, clip=clip)
                if os.path.exists(out_path) and os.path.getsize(out_path) >= min_png:
                    return True
            except Exception as e:
                logger.debug(f"Fallback clip {name} failed: {e}")

        return False
