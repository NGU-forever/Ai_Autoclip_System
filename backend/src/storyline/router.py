"""
OpenStoryline Bridge Router

提供 HTTP API 让 n8n 调用 OpenStoryline 功能
"""

from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sse_starlette.sse import EventSourceResponse

from src.storyline.schemas import (
    StorylineSessionCreate,
    StorylineSessionResponse,
    StorylineSessionDetail,
    NodeExecutionRequest,
    NodeExecutionResponse,
    NodeExecutionResult,
    ArtifactInfo,
    RenderVideoRequest,
    RenderVideoResponse,
    QuickWorkflowRequest,
    QuickWorkflowResponse,
    StorylineCallbackRequest,
    NODE_PRESETS,
    NodePreset,
)
from src.storyline.service import StorylineService
from src.auth.dependencies import get_current_user, RoleChecker

router = APIRouter(prefix="/storyline", tags=["storyline"])


# ============================================================
# Session 管理
# ============================================================

@router.post("/sessions", response_model=StorylineSessionResponse, status_code=201)
async def create_session(
    request: StorylineSessionCreate,
    current_user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """
    创建新的剪辑会话
    
    - **source_media**: 源素材文件路径列表
    - **config**: 输出配置（分辨率、比例等）
    """
    # 注入用户信息
    request.user_id = str(current_user.get("id"))
    request.team_id = current_user.get("team_id")
    
    return await service.create_session(request)


@router.get("/sessions", response_model=List[StorylineSessionResponse])
async def list_sessions(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """列出剪辑会话"""
    return await service.list_sessions(
        user_id=str(current_user.get("id")),
        limit=limit,
        offset=offset
    )


@router.get("/sessions/{session_id}", response_model=StorylineSessionDetail)
async def get_session(
    session_id: str,
    _user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """获取会话详情"""
    return await service.get_session(session_id)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    _user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """删除会话"""
    return await service.delete_session(session_id)


# ============================================================
# 节点执行
# ============================================================

@router.post("/sessions/{session_id}/nodes/{node_name}", response_model=NodeExecutionResponse)
async def execute_node(
    session_id: str,
    node_name: str,
    request: NodeExecutionRequest,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """
    执行剪辑节点
    
    支持的节点：
    - `load_media` - 加载素材
    - `split_shots` - 分镜切割
    - `understand_clips` - 理解视频内容
    - `filter_clips` - 筛选素材
    - `group_clips` - 素材分组
    - `generate_script` - 生成脚本
    - `generate_voiceover` - AI配音
    - `select_bgm` - 选择背景音乐
    - `plan_timeline` - 规划时间线
    - `render_video` - 渲染视频
    
    设置 `wait_for_completion=true` 同步等待结果
    """
    # 覆盖 node_name
    request.node_name = node_name
    
    return await service.execute_node(session_id, request, background_tasks)


@router.get("/sessions/{session_id}/executions/{execution_id}", response_model=NodeExecutionResult)
async def get_execution(
    session_id: str,
    execution_id: str,
    _user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """获取节点执行结果"""
    return await service.get_execution(session_id, execution_id)


# ============================================================
# 产物管理
# ============================================================

@router.get("/sessions/{session_id}/artifacts", response_model=List[ArtifactInfo])
async def list_artifacts(
    session_id: str,
    _user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """列出会话产物"""
    session = await service.get_session(session_id)
    return session.artifacts


@router.get("/sessions/{session_id}/artifacts/{artifact_id}")
async def get_artifact(
    session_id: str,
    artifact_id: str,
    _user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """获取产物详情"""
    return await service._load_artifact(session_id, artifact_id)


@router.get("/sessions/{session_id}/timeline")
async def get_timeline(
    session_id: str,
    _user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """获取当前时间线"""
    return await service._get_current_timeline(session_id)


# ============================================================
# 视频渲染
# ============================================================

@router.post("/sessions/{session_id}/render", response_model=RenderVideoResponse)
async def render_video(
    session_id: str,
    request: RenderVideoRequest,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """
    渲染最终视频
    
    - 设置 `wait_for_completion=true` 同步等待渲染完成
    - 默认异步执行，通过 SSE 或回调接收进度
    """
    return await service.render_video(session_id, request, background_tasks)


# ============================================================
# 节点预设
# ============================================================

@router.get("/node-presets", response_model=List[NodePreset])
async def get_node_presets():
    """获取节点预设配置"""
    return NODE_PRESETS


@router.get("/node-presets/{node_name}")
async def get_node_preset(node_name: str):
    """获取单个节点预设"""
    for preset in NODE_PRESETS:
        if preset.node_name == node_name:
            return preset
    return {"error": "Node preset not found"}


# ============================================================
# 快捷工作流
# ============================================================

@router.post("/quick-workflow", response_model=QuickWorkflowResponse)
async def quick_workflow(
    request: QuickWorkflowRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """
    一键剪辑工作流
    
    自动执行完整流程：加载素材 → 分镜 → 理解 → 脚本 → 配音 → 配乐 → 时间线 → 渲染
    """
    return await service.quick_workflow(request, background_tasks)


# ============================================================
# 回调处理
# ============================================================

@router.post("/callback")
async def handle_callback(
    request: StorylineCallbackRequest,
    service: StorylineService = Depends()
):
    """
    OpenStoryline 回调端点
    
    接收节点执行进度和结果
    """
    return await service.handle_callback(request)


# ============================================================
# SSE 实时流
# ============================================================

@router.get("/sessions/{session_id}/stream")
async def stream_session(
    session_id: str,
    request: Request,
    _user: dict = Depends(get_current_user),
    service: StorylineService = Depends(),
):
    """
    SSE 实时流 - 接收会话事件
    
    事件类型：
    - `node_started` - 节点开始
    - `node_completed` - 节点完成
    - `node_failed` - 节点失败
    - `workflow_progress` - 整体进度
    """
    from src.database import get_redis_client
    import json
    import asyncio
    
    redis = get_redis_client()
    if not redis:
        return {"error": "Redis not connected"}
    
    async def event_generator():
        pubsub = redis.pubsub()
        channel = f"storyline_stream:{session_id}"
        await pubsub.subscribe(channel)
        
        try:
            while True:
                if await request.is_disconnected():
                    break
                
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    data = message['data']
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')
                    yield f"data: {data}\n\n"
                    
                    # 检查是否完成
                    try:
                        parsed = json.loads(data)
                        if parsed.get("type") in ["workflow_completed", "workflow_failed"]:
                            await asyncio.sleep(0.5)
                            break
                    except json.JSONDecodeError:
                        pass
                else:
                    yield ": keepalive\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
    
    return EventSourceResponse(event_generator())


# ============================================================
# 管理接口
# ============================================================

@router.get("/admin/sessions", response_model=List[StorylineSessionResponse])
async def admin_list_all_sessions(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _user: dict = Depends(RoleChecker(["admin"])),
    service: StorylineService = Depends(),
):
    """管理员：列出所有会话"""
    return await service.list_sessions(limit=limit, offset=offset)


@router.post("/admin/cleanup-expired")
async def cleanup_expired_sessions(
    max_age_hours: int = Query(24, ge=1),
    _user: dict = Depends(RoleChecker(["admin"])),
    service: StorylineService = Depends(),
):
    """管理员：清理过期会话"""
    # TODO: 实现清理逻辑
    return {"message": "Cleanup scheduled"}
