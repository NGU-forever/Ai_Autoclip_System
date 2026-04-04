from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    """Uploader 服务用配置；认证已交由 backend 服务处理，不再配置 JWT 相关字段。"""

    project_name: str = "AgentOS Uploader Service"
    version: str = "1.0.0"

    database_url: str = "postgresql://uploader:uploader@localhost:5432/uploader"
    db_pool_min_conn: int = 5
    db_pool_max_conn: int = 50

    # 注意：JWT 配置已移除，认证由 backend 服务统一处理
    # 如需兼容旧配置，保留字段但不再使用
    secret_key: str = "deprecated-use-backend-auth"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    redis_url: str = "redis://localhost:6379/0"

    openstoryline_public_url: str = "http://localhost:7860"
    openstoryline_internal_url: str = "http://storyline:7860"

    storage_root: str = "/app/storage"
    raw_dir: str = "raw"
    intermediate_dir: str = "intermediate"
    exports_dir: str = "exports"
    openstoryline_dir: str = "openstoryline"

    @property
    def raw_path(self) -> str:
        return os.path.join(self.storage_root, self.raw_dir)

    @property
    def intermediate_path(self) -> str:
        return os.path.join(self.storage_root, self.intermediate_dir)

    @property
    def exports_path(self) -> str:
        return os.path.join(self.storage_root, self.exports_dir)

    @property
    def openstoryline_path(self) -> str:
        return os.path.join(self.storage_root, self.openstoryline_dir)

    uploader_chrome_path: str = ""
    uploader_headless: bool = False
    uploader_cookies_dir: str = "uploader/cookies"
    uploader_video_dir: str = "uploader/videos"

    # 浏览器会话配置（从环境变量读取，有默认值）
    browser_heartbeat_timeout: int = 300  # 心跳超时（秒）
    browser_heartbeat_check_interval: int = 10  # 心跳检查间隔（秒）
    browser_qr_validity: int = 300  # 二维码有效期（秒）
    browser_qr_wait_timeout: int = 60  # 二维码等待超时（秒）
    browser_refresh_qr_wait_timeout: int = 30  # 刷新二维码等待超时（秒）
    browser_login_poll_max_time: int = 300  # 登录轮询最大时间（秒）
    browser_max_concurrent_sessions: int = 10  # 最大并发会话数
    
    # 平台特定的二维码有效期（秒）- 差异化配置
    # 抖音约3分钟，视频号和小红书约5分钟
    platform_qr_validity_douyin: int = 180    # 抖音二维码有效期
    platform_qr_validity_tencent: int = 300   # 视频号二维码有效期
    platform_qr_validity_xhs: int = 300       # 小红书二维码有效期
    
    # 二维码过期检测关键词（用于自动刷新）
    qr_expired_keywords: list = ["二维码已过期", "二维码已失效", "请刷新", "已过期", "已失效", "过期"]
    
    # 各平台特定的过期检测选择器（用于更精确的检测）
    qr_expired_selectors: dict = {
        "douyin": [".qrcode-expired", ".expire-text", "[class*='expired']", "[class*='timeout']"],
        "tencent": [".qr-expired", ".expired-tip", "[class*='expired']"],
        "xhs": [".qr-expired", ".expire-text", "[class*='expired']"],
    }
    
    def get_platform_qr_validity(self, platform: str) -> int:
        """获取指定平台的二维码有效期（秒）"""
        mapping = {
            "douyin": self.platform_qr_validity_douyin,
            "tencent": self.platform_qr_validity_tencent,
            "xhs": self.platform_qr_validity_xhs,
        }
        return mapping.get(platform, self.browser_qr_validity)

    @property
    def uploader_cookies_path(self) -> str:
        return os.path.join(self.storage_root, self.uploader_cookies_dir)

    @property
    def uploader_video_path(self) -> str:
        return os.path.join(self.storage_root, self.uploader_video_dir)

    @property
    def uploader_accounts_file(self) -> str:
        return os.path.join(self.uploader_cookies_path, "accounts.json")

    @property
    def uploader_tasks_file(self) -> str:
        return os.path.join(self.uploader_cookies_path, "uploader_tasks.json")

    def get_platform_cookies_path(self, platform: str) -> str:
        return os.path.join(self.uploader_cookies_path, platform)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
