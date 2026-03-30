# -*- coding: utf-8 -*-
"""
二维码登录模型定义
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio


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
    platform: str  # douyin, tencent, xhs
    status: LoginStatus
    qr_code_path: Optional[str] = None  # 二维码图片路径
    cookie_file: Optional[str] = None   # 最终保存的 cookie 文件名
    user_name: Optional[str] = None     # 登录成功后获取的用户名
    error_msg: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    qr_ready: asyncio.Event = field(default_factory=asyncio.Event)  # QR 截图完成信号
    runner: Optional[asyncio.Task] = field(default=None, repr=False, compare=False)
