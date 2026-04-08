import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager


from fastapi import UploadFile

from src.config import settings
from src.config_manager import config_manager
from src.douyin_uploader import douyin_setup, DouYinVideo
from src.douyin_uploader.main import cookie_auth as douyin_cookie_auth
from src.tencent_uploader import weixin_setup, TencentVideo
from src.tencent_uploader.main import cookie_auth as tencent_cookie_auth
from src.xhs_uploader import xiaohongshu_setup, XiaoHongShuVideo
from src.xhs_uploader.main import cookie_auth as xhs_cookie_auth
from src.utils import TencentZoneTypes, get_title_and_hashtags
from src.upload.schemas import AccountResponse, VideoItem
from src.exceptions import NotFoundException
from src.db import AsyncSessionLocal, AccountRepository, TaskRepository

logger = logging.getLogger(__name__)

_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm"})


def _iter_video_files(base: Path, *, recursive: bool):
    if not base.exists():
        return
    if recursive:
        for f in base.rglob("*"):
            if f.is_file() and f.suffix.lower() in _VIDEO_SUFFIXES:
                yield f
    else:
        for f in base.iterdir():
            if f.is_file() and f.suffix.lower() in _VIDEO_SUFFIXES:
                yield f


def _safe_video_path_under_storage(video_id: str) -> Path:
    """
    将 API 中的 video_id 解析为 storage_root 下的绝对路径，禁止跳出 storage。
    video_id 为相对 storage_root 的路径（posix），例如 openstoryline/server_cache/.../a.mp4
    """
    root = Path(settings.storage_root).resolve()
    if not video_id or video_id.strip() != video_id:
        raise NotFoundException("视频不存在")
    rel = Path(video_id)
    if rel.is_absolute() or ".." in rel.parts:
        raise NotFoundException("视频不存在")
    resolved = (root / rel).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise NotFoundException("视频不存在")
    return resolved


def _resolve_publish_video_path(video_id: str) -> Path:
    """列表返回的相对路径，或兼容旧版仅文件名（先 uploader/videos 再 exports）。"""
    # 新格式：相对 storage 的路径
    try:
        p = _safe_video_path_under_storage(video_id)
        if p.is_file():
            return p
    except NotFoundException:
        pass
    flat_uploader = Path(settings.uploader_video_path) / video_id
    if flat_uploader.is_file() and ".." not in Path(video_id).parts:
        return flat_uploader.resolve()
    flat_exports = Path(settings.exports_path) / video_id
    if flat_exports.is_file() and ".." not in Path(video_id).parts:
        return flat_exports.resolve()
    raise NotFoundException(f"视频不存在: {video_id}")


def _ensure_uploader_dirs():
    """确保上传相关目录存在"""
    os.makedirs(settings.uploader_cookies_path, exist_ok=True)
    os.makedirs(settings.uploader_video_path, exist_ok=True)
    # 创建各平台的 cookie 目录
    for platform in ["douyin", "tencent", "xhs"]:
        os.makedirs(settings.get_platform_cookies_path(platform), exist_ok=True)


@asynccontextmanager
async def get_db_session():
    """数据库会话上下文管理器，自动处理提交和回滚"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class UploaderService:
    async def list_accounts(self) -> List[AccountResponse]:
        async with get_db_session() as session:
            repo = AccountRepository(session)
            accounts = await repo.list_all()
            return [
                AccountResponse(
                    id=a.id,
                    platform=a.platform,
                    user_name=a.account_name,
                    cookie_file=a.cookie_file,
                    status=1 if a.is_active else 0,
                )
                for a in accounts
            ]

    async def find_account_by_cookie_file(self, cookie_filename: str) -> Optional[AccountResponse]:
        """按 cookie 文件名查找已登记账号（扫码/持久化会话复用同一文件时需返回已有记录）。"""
        async with get_db_session() as session:
            repo = AccountRepository(session)
            accounts = await repo.list_all()
            for a in accounts:
                if a.cookie_file == cookie_filename:
                    return AccountResponse(
                        id=a.id,
                        platform=a.platform,
                        user_name=a.account_name,
                        cookie_file=a.cookie_file,
                        status=1 if a.is_active else 0,
                    )
            return None

    async def add_account(
        self,
        platform: str,
        user_name: str,
        cookie_filename: str,
    ) -> AccountResponse:
        """
        添加账号，将 cookie 文件移动到对应平台目录
        """
        _ensure_uploader_dirs()

        # 处理 cookie 文件
        cookie_path = self._prepare_cookie_file(platform, cookie_filename)
        if not cookie_path.exists():
            raise NotFoundException(f"Cookie 文件不存在: {cookie_filename}")

        async with get_db_session() as session:
            repo = AccountRepository(session)
            account = await repo.update_or_create_by_platform(
                platform=platform,
                account_name=user_name,
                cookie_file=cookie_filename,
            )
            return AccountResponse(
                id=account.id,
                platform=account.platform,
                user_name=account.account_name,
                cookie_file=account.cookie_file,
                status=1 if account.is_active else 0,
            )

    async def update_account_cookie(
        self,
        platform: str,
        user_name: str,
        cookie_filename: str,
    ) -> AccountResponse:
        """
        更新或添加账号的 cookie。
        如果该平台已有账号，则更新现有账号的 cookie 文件和用户名。
        如果没有，则创建新账号。
        """
        _ensure_uploader_dirs()

        # 处理 cookie 文件
        cookie_path = self._prepare_cookie_file(platform, cookie_filename)
        if not cookie_path.exists():
            raise NotFoundException(f"Cookie 文件不存在: {cookie_filename}")

        async with get_db_session() as session:
            repo = AccountRepository(session)
            account = await repo.update_or_create_by_platform(
                platform=platform,
                account_name=user_name,
                cookie_file=cookie_filename,
            )
            return AccountResponse(
                id=account.id,
                platform=account.platform,
                user_name=account.account_name,
                cookie_file=account.cookie_file,
                status=1 if account.is_active else 0,
            )

    async def delete_account(self, account_id: str) -> bool:
        async with get_db_session() as session:
            repo = AccountRepository(session)
            ok = await repo.deactivate(int(account_id))
            if not ok:
                raise NotFoundException(f"账号不存在: {account_id}")
            return True

    async def get_account(self, account_id: str) -> dict:
        async with get_db_session() as session:
            repo = AccountRepository(session)
            account = await repo.get_by_id(int(account_id))
            if not account:
                raise NotFoundException(f"账号不存在: {account_id}")
            return {
                "id": account.id,
                "platform": account.platform,
                "user_name": account.account_name,
                "cookie_file": account.cookie_file,
                "status": 1 if account.is_active else 0,
            }

    def _get_cookie_file_path(self, account: dict) -> Path:
        """
        获取账号的 cookie 文件路径
        优先查找平台目录，如果找不到则查找根目录（兼容旧数据）
        """
        platform = account.get("platform", "")
        cookie_filename = account.get("cookie_file", "")

        # 优先查找平台目录
        platform_path = Path(settings.get_platform_cookies_path(platform)) / cookie_filename
        if platform_path.exists():
            return platform_path

        # 回退到根目录（兼容旧数据）
        root_path = Path(settings.uploader_cookies_path) / cookie_filename
        if root_path.exists():
            return root_path

        # 返回平台目录路径（即使文件不存在，用于错误提示）
        return platform_path

    def _prepare_cookie_file(self, platform: str, cookie_filename: str) -> Path:
        """
        准备 cookie 文件：确保文件在正确的平台目录下
        返回最终的 cookie 文件路径
        """
        # 查找 cookie 文件（可能在根目录或平台目录）
        source_path = Path(settings.uploader_cookies_path) / cookie_filename
        platform_dir = Path(settings.get_platform_cookies_path(platform))
        platform_cookie_path = platform_dir / cookie_filename

        # 如果文件不在平台目录，移动过去
        if source_path.exists() and not platform_cookie_path.exists():
            # 如果文件在根目录，移动到平台目录
            if source_path.parent == Path(settings.uploader_cookies_path):
                import shutil
                shutil.move(str(source_path), str(platform_cookie_path))
                logger.info(f"Moved cookie file to platform dir: {platform_cookie_path}")

        # 返回最终的 cookie 文件路径
        return platform_cookie_path if platform_cookie_path.exists() else source_path

    async def set_account_status(self, account_id: str, status_val: int) -> None:
        async with get_db_session() as session:
            from sqlalchemy import update
            from src.db.models import Account
            result = await session.execute(
                update(Account)
                .where(Account.id == int(account_id))
                .values(is_active=(status_val != 0), updated_at=datetime.now())
            )
            if result.rowcount == 0:
                raise NotFoundException(f"账号不存在: {account_id}")

    async def check_cookie_valid(self, platform: str, account_id: str) -> bool:
        """
        使用各平台既有 cookie_auth 校验 Playwright storage_state 是否仍可访问创作者页。
        """
        _ensure_uploader_dirs()
        try:
            acc = await self.get_account(account_id)
        except NotFoundException:
            logger.warning(f"Cookie validation failed: account {account_id} not found")
            return False
        if acc.get("platform") != platform:
            logger.warning(f"Cookie validation failed: platform mismatch {platform} != {acc.get('platform')}")
            return False
        cookie_path = self._get_cookie_file_path(acc)
        if not cookie_path.is_file():
            logger.warning(f"Cookie validation failed: cookie file not found {cookie_path}")
            return False
        abs_path = str(cookie_path.resolve())

        try:
            if platform == "douyin":
                return await douyin_cookie_auth(abs_path)
            if platform == "tencent":
                return await tencent_cookie_auth(abs_path)
            if platform == "xhs":
                return await xhs_cookie_auth(abs_path)
            return False
        except Exception as e:
            logger.exception(f"Cookie validation error for {platform}: {e}")
            return False

    def list_videos(self) -> List[VideoItem]:
        _ensure_uploader_dirs()
        items = []
        root = Path(settings.storage_root).resolve()
        seen_paths: set[str] = set()

        scan_specs: List[tuple[Path, bool]] = [
            (Path(settings.uploader_video_path), False),
            (Path(settings.exports_path), False),
            (Path(settings.openstoryline_path), True),
        ]

        for base, recursive in scan_specs:
            for f in _iter_video_files(base, recursive=recursive):
                try:
                    rel_id = f.resolve().relative_to(root).as_posix()
                except ValueError:
                    continue
                key = str(f.resolve())
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                size_mb = f.stat().st_size / (1024 * 1024)
                items.append(
                    VideoItem(
                        id=rel_id,
                        filename=f.name,
                        file_path=str(f.resolve()),
                        size_mb=round(size_mb, 2),
                    )
                )

        items.sort(key=lambda x: Path(x.file_path).stat().st_mtime, reverse=True)
        return items

    def save_uploaded_video(self, file: UploadFile) -> VideoItem:
        _ensure_uploader_dirs()
        ext = Path(file.filename or "video.mp4").suffix or ".mp4"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        dest = Path(settings.uploader_video_path) / unique_name
        with open(dest, "wb") as f:
            content = file.file.read()
            f.write(content)
        size_mb = dest.stat().st_size / (1024 * 1024)
        root = Path(settings.storage_root).resolve()
        rel_id = dest.resolve().relative_to(root).as_posix()
        return VideoItem(
            id=rel_id,
            filename=file.filename or unique_name,
            file_path=str(dest.resolve()),
            size_mb=round(size_mb, 2),
        )

    async def _run_publish(
        self,
        platform: str,
        account_file: str,
        video_path: str,
        title: str,
        tags: List[str],
        category: Optional[str] = None,
        is_draft: bool = False,
        thumbnail_path: Optional[str] = None,
        product_link: Optional[str] = None,
        product_title: Optional[str] = None,
        desc: Optional[str] = None,
        cover_path: Optional[str] = None,
        is_private: bool = False,
        publish_date: Optional[str] = None,
        short_title: Optional[str] = None,
        declare_original: bool = False,
    ):
        """异步执行发布"""
        from datetime import datetime

        # 解析定时发布时间
        publish_datetime = 0
        if publish_date:
            try:
                publish_datetime = datetime.fromisoformat(publish_date.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                logger.warning(f"Invalid publish_date format: {publish_date}, using immediate publish")
                publish_datetime = 0

        if platform == "douyin":
            if not await douyin_setup(account_file, handle=False):
                logger.error("Douyin publish aborted: cookie missing or invalid (%s)", account_file)
                return
            app = DouYinVideo(
                title, video_path, tags, publish_datetime, account_file,
                thumbnail_path=thumbnail_path or "",
                productLink=product_link or "",
                productTitle=product_title or "",
            )
        elif platform == "tencent":
            if not await weixin_setup(account_file, handle=False):
                logger.error("Tencent publish aborted: cookie missing or invalid (%s)", account_file)
                return
            app = TencentVideo(
                title, video_path, tags, publish_datetime, account_file,
                category=category or TencentZoneTypes.LIFESTYLE.value,
                is_draft=is_draft,
                short_title=short_title,
                declare_original=declare_original,
            )
        elif platform == "xhs":
            if not await xiaohongshu_setup(account_file, handle=False):
                logger.error("XHS publish aborted: cookie missing or invalid (%s)", account_file)
                return
            xhs_cover = cover_path or thumbnail_path or ""
            app = XiaoHongShuVideo(
                title,
                video_path,
                tags,
                publish_datetime,
                account_file,
                thumbnail_path=xhs_cover,
                desc=desc,
                is_private=is_private,
            )
        else:
            raise ValueError(f"不支持的平台: {platform}")
        await app.main()

    async def create_publish_task(self, task_data: dict):
        async with get_db_session() as session:
            repo = TaskRepository(session)
            await repo.create(
                task_id=task_data["task_id"],
                platform=task_data["platform"],
                video_id=task_data.get("video_id", ""),
                account_id=task_data.get("account_id"),
                title=task_data.get("title"),
                tags=task_data.get("tags", []),
                request_data=task_data.get("request_data", {}),
            )

    async def update_publish_task_status(self, task_id: str, status: str, error_msg: Optional[str] = None):
        async with get_db_session() as session:
            repo = TaskRepository(session)
            await repo.update_status(task_id, status, error_msg)

    async def get_publish_task(self, task_id: str) -> Optional[dict]:
        async with get_db_session() as session:
            repo = TaskRepository(session)
            task = await repo.get_by_id(task_id)
            if not task:
                return None
            return task.to_dict()

    async def list_publish_tasks(self) -> List[dict]:
        async with get_db_session() as session:
            repo = TaskRepository(session)
            tasks = await repo.list_all(limit=500)
            # 按照创建时间倒序
            tasks.sort(key=lambda x: x.created_at.isoformat() if x.created_at else "", reverse=True)
            return [t.to_dict() for t in tasks]

    async def reconcile_stale_tasks(self) -> int:
        """
        任务对齐（Task Reconciler）：服务启动时调用。
        将所有处于 `running` 状态的任务标记为 `failed`。
        """
        async with get_db_session() as session:
            repo = TaskRepository(session)
            stale = await repo.reconcile_stale()
            if stale:
                logger.warning(
                    "Task Reconciler: 发现并重置了 %d 个孤儿 running 任务 → failed", stale
                )
            else:
                logger.info("Task Reconciler: 无孤儿任务，状态干净。")
            return stale

    async def execute_publish_task(
        self,
        task_id: str,
        platform: str,
        account_id: str,
        video_id: str,
        title: str,
        tags: List[str],
        category: Optional[str] = None,
        is_draft: bool = False,
        thumbnail_path: Optional[str] = None,
        product_link: Optional[str] = None,
        product_title: Optional[str] = None,
        desc: Optional[str] = None,
        cover_path: Optional[str] = None,
        is_private: bool = False,
        publish_date: Optional[str] = None,
        short_title: Optional[str] = None,
        declare_original: bool = False,
    ):
        acc = await self.get_account(account_id)
        cookie_file = self._get_cookie_file_path(acc)

        video_path = _resolve_publish_video_path(video_id)

        await self.update_publish_task_status(task_id, "running")
        try:
            await self._run_publish(
                platform=platform,
                account_file=str(cookie_file),
                video_path=str(video_path),
                title=title,
                tags=tags,
                category=category,
                is_draft=is_draft,
                thumbnail_path=thumbnail_path,
                product_link=product_link,
                product_title=product_title,
                desc=desc,
                cover_path=cover_path,
                is_private=is_private,
                publish_date=publish_date,
                short_title=short_title,
                declare_original=declare_original,
            )
            await self.update_publish_task_status(task_id, "success")
        except Exception as e:
            logger.exception(f"Publish task {task_id} failed: {e}")
            await self.update_publish_task_status(task_id, "failed", error_msg=str(e))