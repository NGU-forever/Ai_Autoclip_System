from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    project_name: str = "AgentOS Enterprise API"
    version: str = "1.0.0"

    # 开发模式：绕过登录认证
    dev_mode: bool = False

    database_url: str
    db_pool_min_conn: int = 5
    db_pool_max_conn: int = 50

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    redis_url: str = "redis://redis:6379/0"

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
    
    # Uploader 服务内部地址（backend 代理用）
    uploader_internal_url: str = "http://uploader:8002"

    @property
    def uploader_cookies_path(self) -> str:
        return os.path.join(self.storage_root, self.uploader_cookies_dir)

    @property
    def uploader_video_path(self) -> str:
        return os.path.join(self.storage_root, self.uploader_video_dir)

    @property
    def uploader_accounts_file(self) -> str:
        return os.path.join(self.uploader_cookies_path, "accounts.json")

    def get_platform_cookies_path(self, platform: str) -> str:
        return os.path.join(self.uploader_cookies_path, platform)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
