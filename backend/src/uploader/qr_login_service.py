# -*- coding: utf-8 -*-
"""
二维码扫码登录服务
用于抖音、视频号等平台的扫码登录，自动获取 Cookie
"""

import asyncio
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import async_playwright, Page

from src.config import settings
from src.uploader.conf import LOCAL_CHROME_PATH
from src.uploader.utils.base_social_media import set_init_script
from src.uploader.utils.douyin_speed_routes import attach_douyin_speed_routes
from src.uploader.utils.playwright_net import (
    goto_with_retry,
    merge_chromium_launch_options,
    platform_label_for_error,
    user_friendly_uploader_error,
)


class LoginStatus(Enum):
    PENDING = "pending"      # 等待扫码
    SCANNING = "scanning"    # 已扫码，等待确认
    SUCCESS = "success"      # 登录成功
    FAILED = "failed"        # 登录失败/超时
    EXPIRED = "expired"      # 二维码过期


@dataclass
class LoginTask:
    """登录任务"""
    id: str
    platform: str  # douyin, tencent
    status: LoginStatus
    qr_code_path: Optional[str] = None  # 二维码图片路径
    cookie_file: Optional[str] = None   # 最终保存的 cookie 文件名
    user_name: Optional[str] = None     # 登录成功后获取的用户名
    error_msg: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    qr_ready: asyncio.Event = field(default_factory=asyncio.Event)  # QR 截图完成信号
    runner: Optional[asyncio.Task] = field(default=None, repr=False, compare=False)


import logging

logger = logging.getLogger(__name__)

class QRLoginService:
    """二维码登录服务"""
    
    def __init__(self):
        self.tasks: Dict[str, LoginTask] = {}
        self._cleanup_old_tasks()
    
    def _cleanup_old_tasks(self):
        """清理超过30分钟的旧任务"""
        now = datetime.now()
        expired = [
            tid for tid, task in self.tasks.items()
            if (now - task.created_at).total_seconds() > 1800
        ]
        for tid in expired:
            del self.tasks[tid]
    
    def _ensure_dirs(self):
        """确保目录存在"""
        os.makedirs(settings.uploader_cookies_path, exist_ok=True)
        qr_dir = Path(settings.storage_root) / "uploader" / "qr_codes"
        os.makedirs(qr_dir, exist_ok=True)
        return qr_dir
    
    async def start_login(self, platform: str) -> LoginTask:
        """开始扫码登录流程"""
        task_id = str(uuid.uuid4())
        qr_dir = self._ensure_dirs()
        
        task = LoginTask(
            id=task_id,
            platform=platform,
            status=LoginStatus.PENDING,
            qr_code_path=str(qr_dir / f"{task_id}.png")
        )
        self.tasks[task_id] = task
        
        # 启动异步任务执行登录流程
        logger.info(f"Starting login task {task_id} for platform {platform}")
        task.runner = asyncio.create_task(self._do_login(task))
        
        return task
    
    async def _do_login(self, task: LoginTask):
        """执行登录流程（在后台运行）"""
        try:
            if task.platform == "douyin":
                await self._login_douyin(task)
            elif task.platform == "tencent":
                await self._login_tencent(task)
            elif task.platform == "xhs":
                await self._login_xhs(task)
            else:
                task.status = LoginStatus.FAILED
                task.error_msg = f"不支持的平台: {task.platform}"
        except asyncio.CancelledError:
            task.status = LoginStatus.FAILED
            if not task.error_msg:
                task.error_msg = "用户取消"
            task.qr_ready.set()
            logger.info("QR login task %s cancelled", task.id)
            raise
        except Exception as e:
            logger.error(f"Error in QR login for {task.platform}: {str(e)}")
            task.status = LoginStatus.FAILED
            task.error_msg = user_friendly_uploader_error(
                e, platform_label_for_error(task.platform)
            )
            task.qr_ready.set()
        finally:
            task.updated_at = datetime.now()
    
    async def _login_douyin(self, task: LoginTask):
        """抖音扫码登录"""
        logger.info(f"Starting Douyin login for task {task.id}")
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
                await asyncio.sleep(1)
                
                logger.info(f"Page loaded: {await page.title()} - {page.url}")

                # 与视频号/小红书一致：轮询 canvas/img，避免首个 selector 命中未加载的占位图（前端白框）
                ok = await self._capture_login_qr_fast(
                    page,
                    task.qr_code_path,
                    "Douyin",
                    min_qr_area=120 * 120,
                    initial_sleep=0.8,
                    poll_interval=0.35,
                    pre_screenshot_sleep=0.12,
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
                    logger.error(f"Failed to generate QR code file at {task.qr_code_path}")
                    task.status = LoginStatus.FAILED
                    task.error_msg = "二维码生成失败"
                    task.qr_ready.set()
                    return
                
                logger.info("QR code generated, waiting for scan...")
                
                # 轮询检测登录状态（最多5分钟）
                for _ in range(300):  # 300 * 1秒 = 5分钟
                    await asyncio.sleep(1)
                    
                    # 检查是否已登录
                    current_url = page.url
                    if "creator-micro/content/upload" in current_url:
                        # 登录成功，保存到抖音目录
                        cookie_filename = f"{uuid.uuid4().hex}.json"
                        platform_cookies_path = Path(settings.get_platform_cookies_path("douyin"))
                        platform_cookies_path.mkdir(parents=True, exist_ok=True)
                        cookie_path = platform_cookies_path / cookie_filename
                        await context.storage_state(path=str(cookie_path))
                        
                        # 尝试获取用户名
                        try:
                            user_name = await page.evaluate("""
                                () => {
                                    const el = document.querySelector('.user-name, .nickname, [class*="user"]');
                                    return el ? el.textContent.trim() : null;
                                }
                            """)
                        except:
                            user_name = None
                        
                        task.status = LoginStatus.SUCCESS
                        task.cookie_file = cookie_filename
                        task.user_name = user_name or f"抖音账号_{task.id[:8]}"
                        break
                    
                    # 检查二维码是否过期
                    try:
                        expired_text = await page.query_selector("text='二维码已过期'")
                        if expired_text:
                            task.status = LoginStatus.EXPIRED
                            break
                    except:
                        pass
                else:
                    # 超时
                    task.status = LoginStatus.EXPIRED
                    task.error_msg = "登录超时，请重试"
                    
            finally:
                await context.close()
                await browser.close()

    def _is_squareish_qr_box(self, w: float, h: float) -> bool:
        """登录二维码多为正方形，过滤长条 banner / 图标。"""
        if w < 56 or h < 56:
            return False
        if w > 520 or h > 520:
            return False
        ratio = w / h if h else 0.0
        return 0.82 <= ratio <= 1.22

    async def _wait_xhs_login_ui(self, page: Page) -> None:
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

    async def get_xhs_login_panel_viewport_rect(self, page: Page) -> Optional[Dict[str, float]]:
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

    async def _switch_xhs_to_scan_qr_mode(self, page: Page) -> None:
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
            logger.debug("No QR candidates inside XHS login panel rect, falling back to full-page pick")
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
        container_rect: Optional[Dict[str, float]] = None,
    ) -> bool:
        """
        抖音/视频号通用：短间隔轮询主页面 + iframe，截最像二维码的 canvas/img；
        避免串行 wait_for_selector 各 5～6s；失败再右侧栏 + 居中裁剪。
        container_rect 可选，用于小红书等将候选限制在登录弹层内。
        """
        min_png = 200
        await asyncio.sleep(initial_sleep)

        for attempt in range(50):
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
                logger.info(f"{label} QR polling canvas/img (attempt {attempt + 1}/50)")

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
    
    async def _login_tencent(self, task: LoginTask):
        """视频号扫码登录"""
        logger.info(f"Starting Tencent Video Channel login for task {task.id}")
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
                # 直接进登录页，避免首页再跳转导致二维码区域延迟或 DOM 不一致
                login_url = "https://channels.weixin.qq.com/login.html"
                logger.info(f"Navigating to {login_url}")
                await goto_with_retry(
                    page,
                    login_url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                    retries=3,
                    delay_sec=2.5,
                    log_label=f"Tencent QR task {task.id} goto",
                )
                await asyncio.sleep(0.6)
                
                logger.info(f"Page loaded: {await page.title()} - {page.url}")
                
                ok = await self._capture_login_qr_fast(page, task.qr_code_path, "Tencent")
                png_ok = (
                    ok
                    and os.path.exists(task.qr_code_path)
                    and os.path.getsize(task.qr_code_path) >= 200
                )
                if png_ok:
                    logger.info(f"Screenshot saved to {task.qr_code_path}")
                    task.qr_ready.set()  # 通知等待方 QR 已就绪
                else:
                    logger.error(f"Failed to generate valid QR PNG at {task.qr_code_path}")
                    task.status = LoginStatus.FAILED
                    task.error_msg = "二维码生成失败"
                    task.qr_ready.set()  # 即使失败也要通知，避免永远阻塞
                    return
                
                logger.info("QR code generated, waiting for scan...")
                
                # 轮询检测登录状态（最多5分钟）
                for _ in range(300):
                    await asyncio.sleep(1)
                    
                    # 检查是否已登录
                    current_url = page.url
                    if "platform/post/create" in current_url or "platform/post/list" in current_url:
                        # 登录成功，保存到视频号目录
                        cookie_filename = f"{uuid.uuid4().hex}.json"
                        platform_cookies_path = Path(settings.get_platform_cookies_path("tencent"))
                        platform_cookies_path.mkdir(parents=True, exist_ok=True)
                        cookie_path = platform_cookies_path / cookie_filename
                        await context.storage_state(path=str(cookie_path))
                        
                        task.status = LoginStatus.SUCCESS
                        task.cookie_file = cookie_filename
                        task.user_name = f"视频号_{task.id[:8]}"
                        break
                    
                    # 检查是否有"已扫码"提示
                    try:
                        scan_text = await page.query_selector("text='已扫码'")
                        if scan_text:
                            task.status = LoginStatus.SCANNING
                    except:
                        pass
                else:
                    task.status = LoginStatus.EXPIRED
                    task.error_msg = "登录超时，请重试"
                    
            finally:
                await context.close()
                await browser.close()
    
    def get_task(self, task_id: str) -> Optional[LoginTask]:
        """获取任务状态"""
        return self.tasks.get(task_id)
    
    async def get_qr_code_data(self, task_id: str) -> Optional[bytes]:
        """获取二维码图片数据。使用 asyncio.Event 等待后台任务完成截图，零延迟通知。"""
        task = self.tasks.get(task_id)
        if not task:
            return None

        # 等待后台 Playwright 任务完成 QR 截图（event.set()），最多等 120 秒
        try:
            await asyncio.wait_for(task.qr_ready.wait(), timeout=120)
        except asyncio.TimeoutError:
            logger.warning(f"QR ready timeout for task {task_id}")
            return None

        # Event 已 set，读取文件
        p = task.qr_code_path
        if p and os.path.exists(p) and os.path.getsize(p) >= 200:
            try:
                with open(p, "rb") as f:
                    return f.read()
            except OSError:
                pass

        return None
    
    async def _login_xhs(self, task: LoginTask):
        """小红书扫码登录"""
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
                
                # 轮询检测登录状态（最多5分钟）
                for _ in range(300):
                    await asyncio.sleep(1)
                    
                    # 检查是否已登录
                    current_url = page.url
                    if "creator.xiaohongshu.com/creator-micro/content/upload" in current_url:
                        # 登录成功，保存到小红书目录
                        cookie_filename = f"{uuid.uuid4().hex}.json"
                        platform_cookies_path = Path(settings.get_platform_cookies_path("xhs"))
                        platform_cookies_path.mkdir(parents=True, exist_ok=True)
                        cookie_path = platform_cookies_path / cookie_filename
                        await context.storage_state(path=str(cookie_path))
                        
                        # 尝试获取用户名
                        try:
                            user_name = await page.evaluate("""
                                () => {
                                    const el = document.querySelector('.user-name, .nickname, [class*="user"], [class*="name"]');
                                    return el ? el.textContent.trim() : null;
                                }
                            """)
                        except:
                            user_name = None
                        
                        task.status = LoginStatus.SUCCESS
                        task.cookie_file = cookie_filename
                        task.user_name = user_name or f"小红书账号_{task.id[:8]}"
                        break
                    
                    # 检查是否有"已扫码"提示
                    try:
                        scan_text = await page.query_selector("text='已扫码'")
                        if scan_text:
                            task.status = LoginStatus.SCANNING
                    except:
                        pass
                else:
                    task.status = LoginStatus.EXPIRED
                    task.error_msg = "登录超时，请重试"
                    
            finally:
                await context.close()
                await browser.close()

    def cancel_task(self, task_id: str):
        """取消登录任务"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = LoginStatus.FAILED
            task.error_msg = "用户取消"
            task.qr_ready.set()
            runner = task.runner
            if runner is not None and not runner.done():
                runner.cancel()
            # 清理二维码文件
            if task.qr_code_path and os.path.exists(task.qr_code_path):
                try:
                    os.remove(task.qr_code_path)
                except OSError:
                    pass


# 全局服务实例
_qr_login_service: Optional[QRLoginService] = None


def get_qr_login_service() -> QRLoginService:
    """获取扫码登录服务实例（单例）"""
    global _qr_login_service
    if _qr_login_service is None:
        _qr_login_service = QRLoginService()
    return _qr_login_service
