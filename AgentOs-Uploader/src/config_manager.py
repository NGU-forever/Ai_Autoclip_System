from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from typing import Dict, Any
from .config import settings as uploader_settings

class ConfigManager:
    """统一的配置管理器，整合所有配置"""

    def __init__(self):
        self._config = {
            "uploader": uploader_settings,
            # 可以在这里添加其他配置
        }

    def get_config(self, module: str = "uploader") -> BaseSettings:
        """获取指定模块的配置"""
        return self._config.get(module, uploader_settings)

    def get(self, key: str, module: str = "uploader", default: Any = None) -> Any:
        """获取配置值"""
        config = self.get_config(module)
        return getattr(config, key, default)

    def get_platform_config(self, platform: str) -> Dict[str, Any]:
        """获取平台特定的配置"""
        config = self.get_config("uploader")
        platform_config = {
            "qr_validity": config.get_platform_qr_validity(platform),
            "cookies_path": config.get_platform_cookies_path(platform),
            "expired_selectors": config.qr_expired_selectors.get(platform, [])
        }
        return platform_config

    def update_config(self, module: str, key: str, value: Any) -> None:
        """更新配置值（注意：这不会持久化到环境变量）"""
        config = self.get_config(module)
        setattr(config, key, value)

    def get_storage_paths(self) -> Dict[str, str]:
        """获取所有存储路径"""
        config = self.get_config("uploader")
        return {
            "raw_path": config.raw_path,
            "intermediate_path": config.intermediate_path,
            "exports_path": config.exports_path,
            "openstoryline_path": config.openstoryline_path,
            "uploader_cookies_path": config.uploader_cookies_path,
            "uploader_video_path": config.uploader_video_path,
            "uploader_accounts_file": config.uploader_accounts_file,
            "uploader_tasks_file": config.uploader_tasks_file
        }

    def get_browser_config(self) -> Dict[str, Any]:
        """获取浏览器相关配置"""
        config = self.get_config("uploader")
        return {
            "heartbeat_timeout": config.browser_heartbeat_timeout,
            "heartbeat_check_interval": config.browser_heartbeat_check_interval,
            "qr_validity": config.browser_qr_validity,
            "qr_wait_timeout": config.browser_qr_wait_timeout,
            "refresh_qr_wait_timeout": config.browser_refresh_qr_wait_timeout,
            "login_poll_max_time": config.browser_login_poll_max_time,
            "max_concurrent_sessions": config.browser_max_concurrent_sessions,
            "expired_keywords": config.qr_expired_keywords,
            "expired_selectors": config.qr_expired_selectors
        }

# 创建全局配置管理器实例
config_manager = ConfigManager()