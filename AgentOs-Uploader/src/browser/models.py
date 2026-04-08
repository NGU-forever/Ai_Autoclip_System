# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import asyncio
import time
from playwright.async_api import BrowserContext, Page

class SessionStatus(Enum):
    INITIALIZING = "initializing"  # 正在初始化浏览器
    READY = "ready"                # 浏览器就绪，二维码已生成
    SCANNING = "scanning"          # 已扫码，等待确认
    TWO_FACTOR_AUTH = "two_factor_auth"  # 需要二步验证（短信验证码）
    SUCCESS = "success"            # 登录成功
    FAILED = "failed"              # 登录失败
    EXPIRED = "expired"            # 二维码过期


class InteractiveSessionStatus(Enum):
    """交互式浏览器会话状态（用于手动登录）"""
    INITIALIZING = "initializing"      # 正在初始化
    WAITING_LOGIN = "waiting_login"    # 等待用户登录
    LOGGED_IN = "logged_in"            # 已登录，保存 cookie 中
    CREATOR_PLATFORM = "creator_platform"  # 已跳转到创作者平台
    CLOSED = "closed"                  # 已关闭


@dataclass
class InteractiveBrowserSession:
    """交互式浏览器会话模型（用于手动登录）"""
    id: str
    platform: str  # douyin, tencent, xhs
    status: InteractiveSessionStatus
    
    # 网络资源
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None
    
    # 业务数据
    cookie_file: Optional[str] = None
    user_name: Optional[str] = None
    account_id: Optional[int] = None  # 关联的数据库账号ID
    error_msg: Optional[str] = None
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: float = field(default_factory=time.time)
    max_lifetime: int = 1800  # 最大存活时间（秒），默认30分钟
    
    # 控制信号
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    _login_success_event: asyncio.Event = field(default_factory=asyncio.Event)
    
    # 后台任务
    _background_tasks: set = field(default_factory=set)
    _screenshot_task: Optional[Any] = None  # 截图推送任务
    _login_detect_task: Optional[Any] = None  # 登录检测任务
    
    # WebSocket 连接引用（用于推送截图）
    _websocket: Optional[Any] = None


@dataclass
class PersistentSession:
    """持久化浏览器会话模型"""
    id: str
    platform: str  # douyin, tencent, xhs
    status: SessionStatus
    
    # 网络资源
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None
    
    # 业务数据
    qr_code_path: Optional[str] = None
    cookie_file: Optional[str] = None
    user_name: Optional[str] = None
    error_msg: Optional[str] = None
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: float = field(default_factory=time.time)
    
    # 控制信号
    qr_ready: asyncio.Event = field(default_factory=asyncio.Event)
    _login_success_event: asyncio.Event = field(default_factory=asyncio.Event)
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    
    # 状态控制
    _background_tasks: set = field(default_factory=set)
    _needs_recovery: bool = False
    _init_url: Optional[str] = None
    _attach_speed_routes: bool = False
    _login_monitors_attached: bool = False
