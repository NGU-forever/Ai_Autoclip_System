"""
OpenStoryline Bridge API Schemas

定义了与 OpenStoryline MCP Server 交互的数据结构
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Session 管理
# ============================================================

class StorylineSessionCreate(BaseModel):
    """创建剪辑会话请求"""
    name: str = Field(..., min_length=1, max_length=200, description="会话名称")
    description: Optional[str] = Field(default=None, description="会话描述")
    source_media: List[str] = Field(default_factory=list, description="源素材路径列表")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="会话配置")
    
    # 视频输出配置
    output_resolution: Optional[Literal["720p", "1080p", "4k"]] = Field(default="1080p")
    aspect_ratio: Optional[Literal["16:9", "4:3", "1:1", "3:4", "9:16"]] = Field(default="16:9")
    output_format: Optional[Literal["mp4", "mov"]] = Field(default="mp4")
    
    # 用户上下文
    user_id: Optional[str] = Field(default=None, description="用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")


class StorylineSessionResponse(BaseModel):
    """会话响应"""
    session_id: str = Field(..., description="会话唯一ID")
    name: str = Field(..., description="会话名称")
    status: Literal["created", "running", "completed", "failed"] = Field(default="created")
    source_media: List[str] = Field(default_factory=list)
    artifacts_dir: str = Field(..., description="产物存储目录")
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(from_attributes=True)


class StorylineSessionDetail(StorylineSessionResponse):
    """会话详情（包含产物列表）"""
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    current_timeline: Optional[Dict[str, Any]] = Field(default=None)
    node_execution_history: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================================
# Node 执行
# ============================================================

class NodeExecutionRequest(BaseModel):
    """节点执行请求"""
    node_name: str = Field(..., description="节点名称")
    artifact_id: Optional[str] = Field(default=None, description="输入产物ID")
    input: Dict[str, Any] = Field(default_factory=dict, description="节点输入参数")
    callback_url: Optional[str] = Field(default=None, description="回调URL")
    wait_for_completion: bool = Field(default=False, description="是否等待完成")
    timeout: int = Field(default=300, ge=1, le=3600, description="超时时间（秒）")


class NodeExecutionResponse(BaseModel):
    """节点执行响应"""
    execution_id: str = Field(..., description="执行实例ID")
    session_id: str = Field(..., description="所属会话ID")
    node_name: str = Field(..., description="节点名称")
    status: Literal["pending", "running", "completed", "failed"] = Field(default="pending")
    input_artifact_id: Optional[str] = Field(default=None)
    output_artifact_id: Optional[str] = Field(default=None)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    error_message: Optional[str] = Field(default=None)


class NodeExecutionResult(BaseModel):
    """节点执行结果详情"""
    execution_id: str
    session_id: str
    node_name: str
    status: str
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]] = Field(default=None)
    error: Optional[Dict[str, Any]] = Field(default=None)
    metrics: Optional[Dict[str, Any]] = Field(default=None)  # 执行耗时、Token数等
    started_at: datetime
    completed_at: Optional[datetime]


# ============================================================
# Artifact 产物
# ============================================================

class ArtifactInfo(BaseModel):
    """产物信息"""
    artifact_id: str
    node_name: str
    type: Literal["media", "script", "voiceover", "bgm", "timeline", "video", "json"]
    data: Dict[str, Any]
    file_path: Optional[str] = Field(default=None)
    file_size: Optional[int] = Field(default=None)
    created_at: datetime


class TimelineInfo(BaseModel):
    """时间线信息"""
    timeline_id: str
    tracks: Dict[str, List[Dict[str, Any]]]  # video, audio, subtitles, bgm
    duration_ms: int
    resolution: Dict[str, int]  # width, height


# ============================================================
# 渲染配置
# ============================================================

class RenderVideoRequest(BaseModel):
    """渲染视频请求"""
    timeline_artifact_id: Optional[str] = Field(default=None, description="时间线产物ID")
    render_config: Dict[str, Any] = Field(default_factory=dict, description="渲染配置")
    
    # 视频参数
    aspect_ratio: Optional[str] = Field(default=None)
    output_max_dimension_px: Optional[int] = Field(default=1080)
    clip_compose_mode: Literal["padding", "crop"] = Field(default="padding")
    bg_color: Optional[List[int]] = Field(default=None)  # [R, G, B]
    crf: int = Field(default=23, ge=10, le=30)
    
    # 字幕参数
    font_color: Optional[List[int]] = Field(default=None)  # [R, G, B, A]
    font_size: int = Field(default=40, ge=28, le=120)
    margin_bottom: int = Field(default=270, ge=40, le=1040)
    stroke_width: int = Field(default=2, ge=0, le=8)
    stroke_color: Optional[List[int]] = Field(default=None)  # [R, G, B, A]
    
    # 音频参数
    bgm_volume_scale: float = Field(default=0.25, ge=0.0, le=3.0)
    tts_volume_scale: float = Field(default=2.0, ge=0.0, le=3.0)
    include_video_audio: bool = Field(default=False)
    video_volume_scale: float = Field(default=1.0, ge=0.0, le=3.0)
    
    # 执行参数
    wait_for_completion: bool = Field(default=True)
    timeout: int = Field(default=600, ge=60, le=3600)


class RenderVideoResponse(BaseModel):
    """渲染视频响应"""
    execution_id: str
    status: str
    output_video_url: Optional[str] = Field(default=None)
    output_video_path: Optional[str] = Field(default=None)
    file_size: Optional[int] = Field(default=None)
    duration_seconds: Optional[float] = Field(default=None)
    started_at: datetime
    completed_at: Optional[datetime]


# ============================================================
# 回调相关
# ============================================================

class StorylineCallbackRequest(BaseModel):
    """Storyline 回调请求"""
    execution_id: str
    session_id: str
    node_name: str
    status: Literal["completed", "failed", "progress"]
    progress_percent: Optional[int] = Field(default=None, ge=0, le=100)
    artifact_id: Optional[str] = Field(default=None)
    output: Optional[Dict[str, Any]] = Field(default=None)
    error: Optional[Dict[str, Any]] = Field(default=None)
    metrics: Optional[Dict[str, Any]] = Field(default=None)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# 节点预设配置
# ============================================================

class NodePreset(BaseModel):
    """节点预设配置"""
    name: str
    description: str
    node_name: str
    default_input: Dict[str, Any]


# 预定义的节点配置
NODE_PRESETS: List[NodePreset] = [
    NodePreset(
        name="自动加载素材",
        description="自动加载并分析素材",
        node_name="load_media",
        default_input={"mode": "auto"}
    ),
    NodePreset(
        name="智能分镜",
        description="基于场景变化自动分镜",
        node_name="split_shots",
        default_input={
            "mode": "auto",
            "min_shot_duration": 1000,
            "max_shot_duration": 10000
        }
    ),
    NodePreset(
        name="内容理解",
        description="AI 理解视频内容生成描述",
        node_name="understand_clips",
        default_input={"mode": "auto"}
    ),
    NodePreset(
        name="智能筛选",
        description="根据用户需求筛选素材",
        node_name="filter_clips",
        default_input={"mode": "auto", "user_request": ""}
    ),
    NodePreset(
        name="素材分组",
        description="按叙事逻辑组织素材",
        node_name="group_clips",
        default_input={"mode": "auto", "user_request": ""}
    ),
    NodePreset(
        name="生成脚本",
        description="基于素材生成配音脚本",
        node_name="generate_script",
        default_input={"mode": "auto", "user_request": ""}
    ),
    NodePreset(
        name="AI 配音",
        description="生成 AI 语音旁白",
        node_name="generate_voiceover",
        default_input={"mode": "auto"}
    ),
    NodePreset(
        name="智能配乐",
        description="选择合适背景音乐",
        node_name="select_bgm",
        default_input={"mode": "auto", "user_request": ""}
    ),
    NodePreset(
        name="规划时间线",
        description="智能规划音视频时间线",
        node_name="plan_timeline",
        default_input={"use_beats": True}
    ),
    NodePreset(
        name="渲染视频",
        description="最终视频渲染输出",
        node_name="render_video",
        default_input={"mode": "auto", "crf": 23}
    ),
]


# ============================================================
# 快捷工作流
# ============================================================

class QuickWorkflowRequest(BaseModel):
    """一键工作流请求"""
    name: str = Field(..., description="工作流名称")
    source_media: List[str] = Field(..., min_length=1, description="源素材路径")
    workflow_type: Literal["auto_edit", "script_first", "template_based"] = Field(default="auto_edit")
    
    # 用户需求
    user_requirements: Optional[str] = Field(default=None, description="用户剪辑需求")
    script_template: Optional[str] = Field(default=None, description="脚本模板")
    skill_name: Optional[str] = Field(default=None, description="使用的 Skill 名称")
    
    # 输出配置
    output_config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    # 分发配置
    distribute_to: Optional[List[str]] = Field(default_factory=list, description="分发平台")
    platform_account_ids: Optional[List[str]] = Field(default_factory=list)
    
    # 回调
    callback_url: Optional[str] = Field(default=None)


class QuickWorkflowResponse(BaseModel):
    """一键工作流响应"""
    workflow_execution_id: str
    session_id: str
    status: str
    message: str
    estimated_duration_seconds: int
    steps: List[Dict[str, str]]
