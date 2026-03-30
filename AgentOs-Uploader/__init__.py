"""
Uploader 模块 - 抖音、视频号等多平台视频上传
从 social-auto-upload 项目迁移
"""
from src.douyin_uploader import douyin_setup, DouYinVideo
from src.tencent_uploader import weixin_setup, TencentVideo

__all__ = [
    "douyin_setup",
    "DouYinVideo",
    "weixin_setup",
    "TencentVideo",
]
