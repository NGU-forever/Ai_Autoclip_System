# -*- coding: utf-8 -*-
"""
QR 登录 Driver 基类

职责：只负责具体的 DOM 操作逻辑
- 如何找二维码
- 如何点击刷新
- 如何检测扫码状态

注意：不负责浏览器生命周期管理（browser/context/page 由 Manager 提供）
"""

from abc import ABC, abstractmethod
from typing import Optional
from playwright.async_api import Page


class BaseQRDriver(ABC):
    """QR 登录 Driver 基类 - 纯 DOM 操作层
    
    设计原则：
    1. 接收 Page 对象作为参数，不创建/销毁浏览器
    2. 只执行平台特定的 UI 交互
    3. 返回明确的结果状态
    """
    
    def __init__(self, platform: str):
        self.platform = platform
    
    @abstractmethod
    async def prepare_login_page(self, page: Page) -> None:
        """准备登录页面
        
        执行平台特定的准备操作：
        - 点击「扫码登录」tab
        - 关闭弹窗/广告
        - 切换到二维码模式
        
        Args:
            page: Playwright Page 对象（由 Manager 提供）
        """
        pass
    
    @abstractmethod
    async def capture_qr_code(self, page: Page, output_path: str) -> bool:
        """捕获二维码图片
        
        Args:
            page: Playwright Page 对象
            output_path: 二维码图片保存路径
            
        Returns:
            是否成功捕获有效二维码图片
        """
        pass
    
    @abstractmethod
    async def detect_scan_status(self, page: Page) -> str:
        """检测当前扫码状态
        
        通过 DOM 检测快速判断状态变化，用于实时反馈。
        
        Args:
            page: Playwright Page 对象
            
        Returns:
            'pending'   - 等待扫码
            'scanning'  - 已扫码，等待确认
            'expired'   - 二维码已过期
            'success'   - 登录成功（可选，Manager 层会二次确认）
            'unknown'   - 无法确定状态
        """
        pass
    
    @abstractmethod
    async def get_user_name(self, page: Page) -> Optional[str]:
        """获取登录用户名
        
        登录成功后从页面提取用户名。
        
        Args:
            page: Playwright Page 对象
            
        Returns:
            用户名，如果无法获取返回 None
        """
        pass
    
    async def refresh_qr_code(self, page: Page) -> bool:
        """刷新二维码（可选实现）
        
        点击页面的「刷新二维码」按钮。
        默认实现返回 False，平台支持时覆盖。
        
        Args:
            page: Playwright Page 对象
            
        Returns:
            是否成功触发刷新
        """
        return False
