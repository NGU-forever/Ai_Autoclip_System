# -*- coding: utf-8 -*-
"""
二维码扫码登录服务
用于抖音、视频号、小红书等平台的扫码登录，自动获取 Cookie

注意：此文件已重构为向后兼容的包装器。
实际实现已移动到 src/qr_login/ 目录下的模块中：
- src/qr_login/models.py    - 模型定义
- src/qr_login/base.py      - 基础类和共享工具
- src/qr_login/douyin.py    - 抖音登录实现
- src/qr_login/tencent.py   - 视频号登录实现
- src/qr_login/xhs.py       - 小红书登录实现
- src/qr_login/__init__.py  - 主服务和导出
"""

# 从新的位置重新导出所有公共 API
from src.qr_login import (
    LoginStatus,
    LoginTask,
    QRLoginService,
    get_qr_login_service,
    DouyinLogin,
    TencentLogin,
    XHSLogin,
    PLATFORM_REGISTRY,
)

__all__ = [
    "LoginStatus",
    "LoginTask",
    "QRLoginService",
    "get_qr_login_service",
    "DouyinLogin",
    "TencentLogin",
    "XHSLogin",
    "PLATFORM_REGISTRY",
]
