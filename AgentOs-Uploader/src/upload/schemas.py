from typing import List, Literal, Optional, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field


# --- 账号 ---
class AccountResponse(BaseModel):
    id: int
    platform: Literal["douyin", "tencent", "xhs"]
    user_name: str
    cookie_file: str
    status: int = 1


class AccountCreate(BaseModel):
    platform: Literal["douyin", "tencent", "xhs"]
    user_name: str = Field(min_length=1, max_length=64)


class AccountUploadCookie(BaseModel):
    platform: Literal["douyin", "tencent", "xhs"]
    user_name: str = Field(min_length=1, max_length=64)


# --- 视频 ---
class VideoItem(BaseModel):
    id: str
    filename: str
    file_path: str
    size_mb: Optional[float] = None


class VideoListResponse(BaseModel):
    items: List[VideoItem]
    total: int


# --- 发布 ---
class PublishRequest(BaseModel):
    platform: Literal["douyin", "tencent", "xhs"]
    account_id: str = Field(description="账号 ID，对应 cookie 文件名或 accounts 中的 id")
    video_id: str = Field(
        description="相对 storage 根目录的路径（posix），如 uploader/videos/xxx.mp4 或 openstoryline/server_cache/.../output_xxx.mp4；兼容旧版仅传文件名"
    )
    title: str = Field(min_length=1, max_length=128)
    tags: List[str] = Field(default_factory=list, max_length=10)
    
    # 视频号专用
    category: Optional[str] = Field(default=None, description="视频号原创分类，如 '生活'")
    is_draft: bool = Field(default=False, description="视频号是否保存为草稿")
    short_title: Optional[str] = Field(default=None, description="视频号短标题（6-16字符）")
    declare_original: bool = Field(default=False, description="视频号是否声明原创")
    
    # 抖音专用
    thumbnail_path: Optional[str] = Field(default=None, description="抖音自定义封面路径")
    product_link: Optional[str] = Field(default=None, description="抖音商品链接")
    product_title: Optional[str] = Field(default=None, description="抖音商品短标题")
    
    # 小红书专用
    desc: Optional[str] = Field(default=None, description="小红书正文描述，缺省则不在正文区重复标题")
    cover_path: Optional[str] = Field(default=None, description="小红书封面本地路径")
    is_private: bool = Field(default=False, description="小红书是否仅自己可见")
    
    # 通用：定时发布（ISO 8601 格式，如 2026-03-23T14:30:00）
    publish_date: Optional[str] = Field(default=None, description="定时发布时间 ISO 格式")


class PublishResponse(BaseModel):
    success: bool
    message: str
    task_id: Optional[str] = None


class PublishTaskItem(BaseModel):
    task_id: str
    platform: str
    account_id: str
    video_id: str
    title: str
    status: Literal["pending", "running", "success", "failed"]
    error_msg: Optional[str] = None
    create_time: str
    update_time: str
    request_data: Dict[str, Any] = Field(default_factory=dict, description="发布请求的原始参数（用于重试）")


class PublishTaskListResponse(BaseModel):
    items: List[PublishTaskItem]
    total: int


# --- 扫码登录 ---
class QRLoginResponse(BaseModel):
    task_id: str
    status: str  # pending, scanning, success, failed, expired
    message: str
    qr_url: Optional[str] = None  # 二维码图片 URL，前端可立即开始加载


class QRLoginStatusResponse(BaseModel):
    task_id: str
    status: str  # pending, scanning, success, failed, expired
    platform: str
    account: Optional[AccountResponse] = None  # 登录成功后返回账号信息
    error: Optional[str] = None


# --- 持久化扫码登录 ---
class PersistentSessionInitResponse(BaseModel):
    sessionId: str  # camelCase for frontend compatibility
    platform: str
    status: str  # initializing, ready, scanning, success, failed, expired
    qrUrl: str  # 二维码图片 URL (camelCase for frontend compatibility)
    message: str
    
    class Config:
        populate_by_name = True


class PersistentSessionStatusResponse(BaseModel):
    sessionId: str  # camelCase for frontend compatibility
    platform: str
    status: str  # initializing, ready, scanning, success, failed, expired
    account: Optional[AccountResponse] = None
    error: Optional[str] = None
    
    class Config:
        populate_by_name = True


class PersistentSessionActionResponse(BaseModel):
    success: bool
    message: str
    status: Optional[str] = None


class PersistentBatchCloseResponse(BaseModel):
    success: bool
    message: str


class PersistentBatchRefreshResponse(BaseModel):
    success: bool
    message: str
    refreshed: int = 0
    skipped: int = 0
    errors: List[str] = Field(default_factory=list)


# --- 平台常量 ---
class PlatformInfo(BaseModel):
    id: str
    name: str


PLATFORMS = [
    PlatformInfo(id="douyin", name="抖音"),
    PlatformInfo(id="tencent", name="视频号"),
    PlatformInfo(id="xhs", name="小红书"),
]
