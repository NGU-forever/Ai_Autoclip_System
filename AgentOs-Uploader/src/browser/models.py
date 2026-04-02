# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import asyncio
import time
from playwright.async_api import BrowserContext, Page

class SessionStatus(Enum):
    INITIALIZING = "initializing"  # 正在初始化浏览器
    READY = "ready"                # 浏览器就绪，二维码已生成
    SCANNING = "scanning"          # 已扫码，等待确认
    SUCCESS = "success"            # 登录成功
    FAILED = "failed"              # 登录失败
    EXPIRED = "expired"            # 二维码过期

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
