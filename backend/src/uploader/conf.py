"""
Uploader 模块配置
从 settings 读取，兼容原有 uploader 的 conf 接口
"""
from pathlib import Path

from src.config import settings

BASE_DIR = Path(settings.storage_root).resolve()
COOKIES_DIR = Path(settings.uploader_cookies_path)
VIDEO_DIR = Path(settings.uploader_video_path)
LOCAL_CHROME_PATH = settings.uploader_chrome_path or ""
LOCAL_CHROME_HEADLESS = settings.uploader_headless
