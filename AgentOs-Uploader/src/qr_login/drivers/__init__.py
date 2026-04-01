# -*- coding: utf-8 -*-
"""
QR 登录 Driver 工厂

提供平台特定的 Driver 实例。
"""

from typing import Dict, Type

from .base import BaseQRDriver
from .douyin import DouyinDriver
from .tencent import TencentDriver
from .xhs import XHSDriver

# Driver 注册表
_drivers: Dict[str, Type[BaseQRDriver]] = {
    "douyin": DouyinDriver,
    "tencent": TencentDriver,
    "xhs": XHSDriver,
}


def get_driver(platform: str) -> BaseQRDriver:
    """获取平台对应的 QR Driver
    
    Args:
        platform: 平台标识 ('douyin', 'tencent', 'xhs')
        
    Returns:
        对应平台的 Driver 实例
        
    Raises:
        ValueError: 不支持的平台
    """
    driver_class = _drivers.get(platform)
    if not driver_class:
        raise ValueError(f"Unsupported platform: {platform}. Supported: {list(_drivers.keys())}")
    return driver_class()


def register_driver(platform: str, driver_class: Type[BaseQRDriver]) -> None:
    """注册新的平台 Driver
    
    用于扩展支持新的平台。
    
    Args:
        platform: 平台标识
        driver_class: Driver 类（继承自 BaseQRDriver）
    """
    _drivers[platform] = driver_class


def list_supported_platforms() -> list:
    """获取支持的平台列表"""
    return list(_drivers.keys())


__all__ = [
    'BaseQRDriver',
    'DouyinDriver',
    'TencentDriver',
    'XHSDriver',
    'get_driver',
    'register_driver',
    'list_supported_platforms',
]
