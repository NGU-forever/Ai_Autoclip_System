# -*- coding: utf-8 -*-
"""
持久化浏览器会话服务 (向前兼容代理)

警告：该文件已被重构为模块化包 `src.browser/`。
建议新代码直接从 `src.browser` 导入对应组件。
"""

import logging
from typing import Optional

# 代理导入
from src.browser import (
    get_persistent_browser_manager,
    PersistentSession,
    SessionStatus,
)

logger = logging.getLogger(__name__)

# 为维持旧代码中的 get_persistent_browser_manager_sync 的兼容性
# 注意：这在 manager 尚未异步启动前可能返回 None
from src.browser.manager import SessionManager

def get_persistent_browser_manager_sync() -> Optional[SessionManager]:
    """同步获取管理器实例（向前兼容）"""
    try:
        return SessionManager()
    except Exception:
        return None

# 如果有文件需要这个模块级别的导出
__all__ = [
    "get_persistent_browser_manager",
    "get_persistent_browser_manager_sync",
    "PersistentSession",
    "SessionStatus",
]
