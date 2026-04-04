"""
Uploader 服务代理路由
所有 /api/admin/uploader/* 请求由 backend 统一认证后转发到 uploader 服务
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from src.auth.dependencies import get_current_user
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Uploader 服务地址（Docker 内网或本地开发）
UPLOADER_BASE_URL = getattr(settings, 'uploader_internal_url', 'http://uploader:8002')

# 需要流式响应的内容类型
STREAMING_CONTENT_TYPES = {
    'video/', 'audio/', 'image/', 'application/octet-stream',
    'application/pdf', 'text/event-stream'
}


def _should_stream_response(content_type: str | None) -> bool:
    """判断是否应该使用流式响应"""
    if not content_type:
        return False
    content_type = content_type.lower()
    return any(content_type.startswith(ct) for ct in STREAMING_CONTENT_TYPES)


async def _proxy_request(
    request: Request,
    path: str,
    user: dict,
    method: str = None,
) -> Response:
    """
    代理请求到 uploader 服务
    
    Args:
        request: 原始请求
        path: 目标路径（不含 /api/admin/uploader 前缀）
        user: 当前用户信息（由 backend 认证后提供）
        method: 请求方法（默认使用 request.method）
    """
    method = method or request.method
    
    # 构建目标 URL
    target_url = f"{UPLOADER_BASE_URL}/api/admin/uploader{path}"
    if request.query_params:
        target_url = f"{target_url}?{request.query_params}"
    
    # 准备 headers（添加用户信息，移除 host）
    headers = dict(request.headers)
    headers.pop('host', None)
    headers.pop('authorization', None)  # 移除原始 Authorization header
    headers.pop('cookie', None)  # 移除原始 cookie，避免冲突
    
    # 添加用户身份信息（uploader 服务通过 header 获取用户信息）
    headers['X-User-Id'] = str(user.get('id', ''))
    headers['X-User-Role'] = str(user.get('role', 'user'))
    
    # 读取请求体
    body = await request.body()
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # 转发请求
            response = await client.request(
                method=method,
                url=target_url,
                headers=headers,
                content=body,
                follow_redirects=False,
            )
    except httpx.ConnectError as e:
        logger.error(f"无法连接到 uploader 服务: {e}")
        raise HTTPException(
            status_code=503,
            detail="Uploader 服务暂不可用，请稍后重试"
        )
    except httpx.TimeoutException as e:
        logger.error(f"Uploader 服务请求超时: {e}")
        raise HTTPException(
            status_code=504,
            detail="Uploader 服务响应超时"
        )
    except Exception as e:
        logger.error(f"代理请求失败: {e}")
        raise HTTPException(
            status_code=502,
            detail="代理请求失败"
        )
    
    # 处理响应
    content_type = response.headers.get('content-type', '')
    
    # 对于流式内容（视频、图片等）使用 StreamingResponse
    if _should_stream_response(content_type):
        return StreamingResponse(
            content=response.aiter_raw(),
            status_code=response.status_code,
            headers={
                k: v for k, v in response.headers.items()
                if k.lower() not in ('content-encoding', 'transfer-encoding', 'connection')
            },
            background=BackgroundTask(response.aclose)
        )
    
    # 普通响应
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers={
            k: v for k, v in response.headers.items()
            if k.lower() not in ('content-encoding', 'transfer-encoding', 'connection', 'content-length')
        },
        media_type=content_type or None,
    )


# 所有 /api/admin/uploader/* 的 HTTP 方法都代理到 uploader 服务
@router.api_route(
    "/uploader/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    include_in_schema=False,
)
async def proxy_to_uploader(
    request: Request,
    path: str,
    user: dict = Depends(get_current_user),
):
    """
    代理所有 uploader 相关请求到 uploader 服务。
    
    - 先由 backend 进行 JWT 认证
    - 认证通过后，添加 X-User-Id 和 X-User-Role header 转发到 uploader
    - uploader 服务不再进行 JWT 验证，只信任 backend 添加的 header
    """
    # 处理根路径
    if not path:
        path = "/"
    else:
        path = f"/{path}"
    
    return await _proxy_request(request, path, user)


# WebSocket 代理（特殊处理）
@router.websocket("/uploader/ws/{path:path}")
async def proxy_uploader_websocket(websocket: Any, path: str):
    """
    WebSocket 代理到 uploader 服务。
    
    注意：WebSocket 认证在握手阶段完成，backend 先验证，然后转发到 uploader。
    """
    from fastapi import WebSocket
    from starlette.websockets import WebSocketDisconnect
    
    if not isinstance(websocket, WebSocket):
        await websocket.close(code=1002)
        return
    
    # 这里需要特殊处理 WebSocket 认证和转发
    # 暂时返回错误，建议直接连接 uploader 服务（通过 nginx 或前端配置）
    await websocket.accept()
    await websocket.send_json({
        "error": "WebSocket connections should go directly to uploader service"
    })
    await websocket.close(code=1002)
