import asyncio
import os
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse

from src.auth.dependencies import get_current_user
from src.exceptions import NotFoundException
from src.uploader.schemas import (
    AccountResponse,
    PLATFORMS,
    PersistentBatchCloseResponse,
    PersistentBatchRefreshResponse,
    PersistentSessionActionResponse,
    PersistentSessionInitResponse,
    PersistentSessionStatusResponse,
    PublishRequest,
    PublishResponse,
    QRLoginResponse,
    QRLoginStatusResponse,
    VideoItem,
    VideoListResponse,
)
from src.uploader.service import UploaderService, _resolve_publish_video_path
from src.uploader.qr_login_service import get_qr_login_service, LoginStatus
from src.uploader.persistent_browser_service import (
    get_persistent_browser_manager,
    SessionStatus,
)

router = APIRouter(prefix="/uploader", tags=["uploader"])


def get_uploader_service() -> UploaderService:
    return UploaderService()


# --- 账号 ---
@router.get("/accounts", response_model=List[AccountResponse])
async def list_accounts(
    _user: dict = Depends(get_current_user),
    service: UploaderService = Depends(get_uploader_service),
):
    """获取已配置的发布账号列表"""
    return service.list_accounts()


@router.post("/accounts", response_model=AccountResponse)
async def add_account(
    platform: str = Form(..., description="平台：douyin 或 tencent"),
    user_name: str = Form(..., description="账号昵称/标识"),
    file: UploadFile = File(..., description="Cookie JSON 文件（Playwright storage_state 格式）"),
    _user: dict = Depends(get_current_user),
    service: UploaderService = Depends(get_uploader_service),
):
    """
    添加账号：上传 Cookie 文件并登记。
    需先通过 Playwright 扫码登录获取 storage_state，保存为 JSON 后上传。
    Cookie 文件将保存到对应平台目录：cookies/{platform}/
    """
    from src.config import settings

    # 确保平台目录存在
    platform_cookies_path = Path(settings.get_platform_cookies_path(platform))
    platform_cookies_path.mkdir(parents=True, exist_ok=True)
    
    ext = Path(file.filename or "cookie.json").suffix or ".json"
    cookie_filename = f"{uuid.uuid4().hex}{ext}"
    dest = platform_cookies_path / cookie_filename
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    return service.add_account(
        platform=platform,
        user_name=user_name,
        cookie_filename=cookie_filename,
    )


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str,
    _user: dict = Depends(get_current_user),
    service: UploaderService = Depends(get_uploader_service),
):
    """删除账号"""
    service.delete_account(account_id)
    return {"success": True}


# --- 扫码登录 ---
@router.post("/accounts/qr-login", response_model=QRLoginResponse)
async def start_qr_login(
    platform: str = Query(..., description="平台：douyin 或 tencent"),
    _user: dict = Depends(get_current_user),
):
    """
    启动扫码登录流程。
    返回 task_id，用于后续获取二维码和查询登录状态。
    """
    if platform not in ["douyin", "tencent", "xhs"]:
        raise HTTPException(status_code=400, detail="不支持的平台，仅支持 douyin、tencent 或 xhs")
    
    qr_service = get_qr_login_service()
    task = await qr_service.start_login(platform)
    
    return QRLoginResponse(
        task_id=task.id,
        status=task.status.value,
        message="请使用抖音/微信/小红书扫码登录",
        qr_url=f"/api/admin/uploader/accounts/qr-login/{task.id}/qr-code",
    )


@router.get("/accounts/qr-login/{task_id}/qr-code")
async def get_qr_code_image(
    task_id: str,
):
    """
    获取登录二维码图片。
    二维码有效期约5分钟，需尽快扫码。
    """
    qr_service = get_qr_login_service()
    
    # 先检查任务是否存在
    task = qr_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="登录任务不存在")
    
    # 检查任务是否失败
    if task.status.value == "failed":
        raise HTTPException(status_code=400, detail=f"登录任务失败: {task.error_msg or '未知错误'}")
    
    # 获取二维码数据（内部会等待文件生成）
    qr_data = await qr_service.get_qr_code_data(task_id)
    
    if not qr_data:
        raise HTTPException(status_code=404, detail="二维码尚未生成，请稍后重试")
    
    return StreamingResponse(
        iter([qr_data]),
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@router.get("/accounts/qr-login/{task_id}/status", response_model=QRLoginStatusResponse)
async def get_qr_login_status(
    task_id: str,
    _user: dict = Depends(get_current_user),
    service: UploaderService = Depends(get_uploader_service),
):
    """
    查询扫码登录状态。
    前端应轮询此接口（建议每2秒一次），直到状态为 success 或失败。
    """
    qr_service = get_qr_login_service()
    task = qr_service.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="登录任务不存在")
    
    response = QRLoginStatusResponse(
        task_id=task.id,
        status=task.status.value,
        platform=task.platform,
    )
    
    # 如果登录成功：新建账号或返回已绑定的同一 cookie 文件对应账号
    if task.status == LoginStatus.SUCCESS and task.cookie_file:
        existing = service.find_account_by_cookie_file(task.cookie_file)
        if existing:
            response.account = existing
        else:
            response.account = service.add_account(
                platform=task.platform,
                user_name=task.user_name or f"{task.platform}_{task.id[:8]}",
                cookie_filename=task.cookie_file,
            )
    
    if task.error_msg:
        response.error = task.error_msg
        
    return response


@router.post("/accounts/qr-login/{task_id}/cancel")
async def cancel_qr_login(
    task_id: str,
    _user: dict = Depends(get_current_user),
):
    """取消扫码登录任务"""
    qr_service = get_qr_login_service()
    qr_service.cancel_task(task_id)
    return {"success": True}


# --- 视频 ---
@router.get("/videos", response_model=VideoListResponse)
async def list_videos(
    _user: dict = Depends(get_current_user),
    service: UploaderService = Depends(get_uploader_service),
):
    """获取待上传视频列表"""
    items = service.list_videos()
    return VideoListResponse(items=items, total=len(items))


@router.post("/videos", response_model=VideoItem)
async def upload_video(
    file: UploadFile = File(...),
    _user: dict = Depends(get_current_user),
    service: UploaderService = Depends(get_uploader_service),
):
    """上传视频到待发布列表"""
    return service.save_uploaded_video(file)


@router.get("/video-stream/{video_id:path}")
async def stream_video(
    video_id: str,
    _user: dict = Depends(get_current_user),
):
    """按相对 storage 的路径流式返回视频（供前端预览），兼容旧版仅文件名。"""
    path = _resolve_publish_video_path(video_id)
    media = "application/octet-stream"
    suf = path.suffix.lower()
    if suf == ".mp4":
        media = "video/mp4"
    elif suf == ".webm":
        media = "video/webm"
    elif suf == ".mov":
        media = "video/quicktime"
    return FileResponse(path, media_type=media, filename=path.name)


@router.post("/upload-cover", response_model=VideoItem)
async def upload_cover(
    file: UploadFile = File(..., description="封面图片文件（jpg/png）"),
    _user: dict = Depends(get_current_user),
):
    """
    上传封面图片（抖音/小红书）。
    返回保存的文件路径，用于发布时指定封面。
    """
    from src.config import settings
    import os
    
    os.makedirs(settings.uploader_video_path, exist_ok=True)
    ext = Path(file.filename or "cover.jpg").suffix or ".jpg"
    unique_name = f"cover_{uuid.uuid4().hex}{ext}"
    dest = Path(settings.uploader_video_path) / unique_name
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    root = Path(settings.storage_root).resolve()
    rel_id = dest.resolve().relative_to(root).as_posix()
    return VideoItem(
        id=rel_id,
        filename=file.filename or unique_name,
        file_path=str(dest.resolve()),
        size_mb=round(dest.stat().st_size / (1024 * 1024), 2) if dest.exists() else None,
    )


# --- 发布 ---
@router.post("/publish", response_model=PublishResponse)
async def publish(
    req: PublishRequest,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user),
    service: UploaderService = Depends(get_uploader_service),
):
    """
    提交发布任务（后台执行）。
    抖音/视频号会打开浏览器完成上传，请确保环境已安装 Playwright Chromium。
    """
    try:
        cookie_ok = await run_in_threadpool(
            service.check_cookie_valid,
            req.platform,
            req.account_id,
        )
    except NotFoundException:
        raise
    if not cookie_ok:
        try:
            await run_in_threadpool(service.set_account_status, req.account_id, 0)
        except NotFoundException:
            pass
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "UPLOADER_COOKIE_INVALID",
                "platform": req.platform,
                "message": "登录已失效，请重新扫码登录",
            },
        )

    background_tasks.add_task(
        service.publish,
        platform=req.platform,
        account_id=req.account_id,
        video_id=req.video_id,
        title=req.title,
        tags=req.tags,
        category=req.category,
        is_draft=req.is_draft,
        thumbnail_path=req.thumbnail_path,
        product_link=req.product_link,
        product_title=req.product_title,
        desc=req.desc,
        cover_path=req.cover_path,
        is_private=req.is_private,
        publish_date=req.publish_date,
        short_title=req.short_title,
        declare_original=req.declare_original,
    )
    return PublishResponse(
        success=True,
        message="发布任务已提交，正在后台执行",
    )


# --- 平台信息 ---
@router.get("/platforms")
async def list_platforms(_user: dict = Depends(get_current_user)):
    """获取支持的发布平台列表"""
    return {"platforms": PLATFORMS}


# --- 持久化扫码登录 ---
@router.post("/accounts/qr-persistent/init", response_model=PersistentSessionInitResponse)
async def init_persistent_session(
    platform: str = Query(..., description="平台：douyin 或 tencent"),
    _user: dict = Depends(get_current_user),
):
    """
    初始化持久化扫码登录会话。
    后台会启动浏览器实例并保持运行，直到心跳超时或手动关闭。
    """
    if platform not in ["douyin", "tencent", "xhs"]:
        raise HTTPException(status_code=400, detail="不支持的平台，仅支持 douyin、tencent 或 xhs")
    
    manager = await get_persistent_browser_manager()
    session = await manager.create_session(platform)
    
    # 等待二维码生成（最多60秒）
    try:
        await asyncio.wait_for(session.qr_ready.wait(), timeout=60)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=500, detail="二维码生成超时")
    
    if session.status == SessionStatus.FAILED:
        raise HTTPException(status_code=500, detail=session.error_msg or "初始化失败")
    
    return PersistentSessionInitResponse(
        sessionId=session.id,
        platform=platform,
        status=session.status.value,
        qrUrl=f"/api/admin/uploader/accounts/qr-persistent/{session.id}/qr-code",
        message="请使用抖音/微信/小红书扫码登录",
    )


@router.post("/accounts/qr-persistent/{session_id}/heartbeat", response_model=PersistentSessionActionResponse)
async def persistent_session_heartbeat(
    session_id: str,
    _user: dict = Depends(get_current_user),
):
    """
    更新会话心跳，保持浏览器实例存活。
    建议每10秒调用一次。
    """
    manager = await get_persistent_browser_manager()
    success = manager.update_heartbeat(session_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    
    session = manager.get_session(session_id)
    return PersistentSessionActionResponse(
        success=True,
        message="心跳更新成功",
        status=session.status.value if session else None,
    )


@router.post("/accounts/qr-persistent/{session_id}/refresh-qr", response_model=PersistentSessionActionResponse)
async def refresh_persistent_qr(
    session_id: str,
    _user: dict = Depends(get_current_user),
):
    """
    刷新二维码（在同一浏览器会话中）。
    重新加载页面并截取新的二维码图片。
    """
    manager = await get_persistent_browser_manager()
    ok, err = await manager.refresh_session_qr_wait(session_id)
    if not ok:
        if err == "会话不存在":
            raise HTTPException(status_code=404, detail=err or "会话不存在")
        raise HTTPException(status_code=500, detail=err or "刷新二维码失败")
    session = manager.get_session(session_id)
    return PersistentSessionActionResponse(
        success=True,
        message="二维码已刷新",
        status=session.status.value if session else None,
    )


@router.post("/accounts/qr-persistent/close-all", response_model=PersistentBatchCloseResponse)
async def close_all_persistent_sessions(
    _user: dict = Depends(get_current_user),
):
    """关闭所有持久化扫码浏览器会话（前端离开分发页等场景）。"""
    manager = await get_persistent_browser_manager()
    await manager.close_all_sessions()
    return PersistentBatchCloseResponse(success=True, message="已关闭所有持久化浏览器会话")


@router.post("/accounts/qr-persistent/refresh-all", response_model=PersistentBatchRefreshResponse)
async def refresh_all_persistent_sessions(
    _user: dict = Depends(get_current_user),
):
    """依次刷新所有可刷新状态的持久化会话（不关闭浏览器，仅重载页面并更新二维码）。"""
    manager = await get_persistent_browser_manager()
    result = await manager.refresh_all_sessions()
    msg = f"已刷新 {result['refreshed']} 个会话，跳过 {result['skipped']} 个"
    if result["errors"]:
        msg += "；" + "; ".join(result["errors"][:8])
    return PersistentBatchRefreshResponse(
        success=len(result["errors"]) == 0,
        message=msg,
        refreshed=result["refreshed"],
        skipped=result["skipped"],
        errors=result["errors"],
    )


@router.get("/accounts/qr-persistent/{session_id}/qr-code")
async def get_persistent_qr_code(
    session_id: str,
):
    """
    获取持久化会话的二维码图片。
    """
    manager = await get_persistent_browser_manager()
    session = manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    qr_data = await manager.get_qr_code_data(session_id)
    
    if not qr_data:
        raise HTTPException(status_code=404, detail="二维码尚未生成")
    
    return StreamingResponse(
        iter([qr_data]),
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@router.get("/accounts/qr-persistent/{session_id}/status", response_model=PersistentSessionStatusResponse)
async def get_persistent_session_status(
    session_id: str,
    _user: dict = Depends(get_current_user),
    service: UploaderService = Depends(get_uploader_service),
):
    """
    查询持久化会话的登录状态。
    登录成功后会自动创建账号。
    """
    manager = await get_persistent_browser_manager()
    session = manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    response = PersistentSessionStatusResponse(
        sessionId=session.id,
        platform=session.platform,
        status=session.status.value,
    )
    
    # 如果登录成功：新建账号或返回已绑定的同一 cookie 文件对应账号
    if session.status == SessionStatus.SUCCESS and session.cookie_file:
        existing = service.find_account_by_cookie_file(session.cookie_file)
        if existing:
            response.account = existing
        else:
            response.account = service.add_account(
                platform=session.platform,
                user_name=session.user_name or f"{session.platform}_{session.id[:8]}",
                cookie_filename=session.cookie_file,
            )
    
    if session.error_msg:
        response.error = session.error_msg
    
    return response


@router.post("/accounts/qr-persistent/{session_id}/cancel")
async def cancel_persistent_session(
    session_id: str,
    _user: dict = Depends(get_current_user),
):
    """
    取消并关闭持久化会话，释放浏览器资源。
    """
    manager = await get_persistent_browser_manager()
    session = manager.get_session(session_id)
    
    if not session:
        return {"success": True, "message": "会话已关闭"}
    
    await manager.close_session(session_id)
    
    return {"success": True, "message": "会话已关闭"}
