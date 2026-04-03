# -*- coding: utf-8 -*-
"""抖音创作者登录页：拦截字体/媒体与部分第三方图片，加快加载且不误伤主站二维码资源。"""

from playwright.async_api import BrowserContext, Route


def _should_abort_third_party_image(url: str) -> bool:
    lower = url.lower()
    needles = (
        "google-analytics",
        "googletagmanager",
        "doubleclick",
        "facebook.com/tr",
        "hm.baidu.com",
    )
    return any(n in lower for n in needles)


async def attach_douyin_speed_routes(context: BrowserContext) -> None:
    async def handler(route: Route) -> None:
        req = route.request
        rt = req.resource_type
        if rt in ("font", "media"):
            await route.abort()
            return
        if rt == "image" and _should_abort_third_party_image(req.url):
            await route.abort()
            return
        await route.continue_()

    await context.route("**/*", handler)
