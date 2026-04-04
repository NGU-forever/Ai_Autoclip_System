from pathlib import Path
from typing import List
import asyncio
import os
import json
from src.config import settings

SOCIAL_MEDIA_DOUYIN = "douyin"
SOCIAL_MEDIA_TENCENT = "tencent"
SOCIAL_MEDIA_TIKTOK = "tiktok"
SOCIAL_MEDIA_BILIBILI = "bilibili"
SOCIAL_MEDIA_KUAISHOU = "kuaishou"


def get_supported_social_media() -> List[str]:
    return [SOCIAL_MEDIA_DOUYIN, SOCIAL_MEDIA_TENCENT, SOCIAL_MEDIA_TIKTOK, SOCIAL_MEDIA_KUAISHOU]


def get_cli_action() -> List[str]:
    return ["upload", "login", "watch"]


async def set_init_script(context):
    stealth_js_path = Path(__file__).parent / "stealth.min.js"
    await context.add_init_script(path=str(stealth_js_path))
    
    # 网络请求拦截逻辑：优化内存使用
    async def intercept_route(route):
        try:
            resource_type = route.request.resource_type
            url = route.request.url.lower()
            
            # 1. 拦截大内存消耗的媒体流和字体（上传不需要看视频或加载外部字体）
            if resource_type in ['media', 'font']:
                await route.abort()
                return
                
            # 2. 拦截非关键图片，放行二维码、验证码等带有鉴权特征的图片
            if resource_type == 'image':
                allow_keywords = ['qr', 'login', 'captcha', 'passport', 'sso', 'auth', 'verify', 'account']
                if any(k in url for k in allow_keywords) or url.startswith('data:'):
                    await route.continue_()
                else:
                    await route.abort()
                return

            # 3. 拦截常见的日志上报、广告和数据追踪请求
            blocked_keywords = ['log.', 'analytics', 'tracker', 'metrics', 'doubleclick', 'adservice', 'beacon', 'tj.']
            if any(k in url for k in blocked_keywords):
                await route.abort()
                return
                
            await route.continue_()
        except Exception:
            # 忽略已经被处理的路由异常
            pass

    try:
        await context.route("**/*", intercept_route)
    except Exception:
        pass

    return context
