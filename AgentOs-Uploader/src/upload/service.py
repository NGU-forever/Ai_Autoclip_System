import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, UploadFile

from src.config import settings
from uploader.douyin_uploader import douyin_setup, DouYinVideo
from uploader.douyin_uploader.main import cookie_auth as douyin_cookie_auth
from uploader.tencent_uploader import weixin_setup, TencentVideo
from uploader.tencent_uploader.main import cookie_auth as tencent_cookie_auth
from uploader.xhs_uploader import xiaohongshu_setup, XiaoHongShuVideo
from uploader.xhs_uploader.main import cookie_auth as xhs_cookie_auth
from uploader.utils import TencentZoneTypes, get_title_and_hashtags
from src.upload.schemas import AccountResponse, VideoItem
from src.exceptions import NotFoundException

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


def _accounts_path() -> Path:
    return Path(settings.uploader_accounts_file)


def _ensure_uploader_dirs():
    """确保上传相关目录存在"""
    os.makedirs(settings.uploader_cookies_path, exist_ok=True)
    os.makedirs(settings.uploader_video_path, exist_ok=True)
    # 创建各平台的 cookie 目录
    for platform in ["douyin", "tencent", "xhs"]:
        os.makedirs(settings.get_platform_cookies_path(platform), exist_ok=True)


def _load_accounts() -> List[dict]:
    _ensure_uploader_dirs()
    p = _accounts_path()
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_accounts(accounts: List[dict]):
    _ensure_uploader_dirs()
    p = _accounts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


class UploaderService:
    def list_accounts(self) -> List[AccountResponse]:
        # 仅以 accounts.json 为准，不扫描 cookies/{platform}/ 下的 persistent_*.json。
        # 否则目录里多个历史 cookie 文件会被自动登记成多条账号，与「实际只维护一个账号」的前端预期不一致。
        accounts = _load_accounts()
        return [
            AccountResponse(
                id=a["id"],
                platform=a["platform"],
                user_name=a["user_name"],
                cookie_file=a["cookie_file"],
                status=a.get("status", 1),
            )
            for a in accounts
        ]

    def find_account_by_cookie_file(self, cookie_filename: str) -> Optional[AccountResponse]:
        """按 cookie 文件名查找已登记账号（扫码/持久化会话复用同一文件时需返回已有记录）。"""
        for a in _load_accounts():
            if a.get("cookie_file") == cookie_filename:
                return AccountResponse(
                    id=a["id"],
                    platform=a["platform"],
                    user_name=a["user_name"],
                    cookie_file=a["cookie_file"],
                    status=a.get("status", 1),
                )
        return None

    def add_account(
        self,
        platform: str,
        user_name: str,
        cookie_filename: str,
    ) -> AccountResponse:
        """
        添加账号，将 cookie 文件移动到对应平台目录
        """
        _ensure_uploader_dirs()
        
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
        
        # 检查最终的 cookie 文件路径
        final_cookie_path = platform_cookie_path if platform_cookie_path.exists() else source_path
        if not final_cookie_path.exists():
            raise NotFoundException(f"Cookie 文件不存在: {cookie_filename}")

        accounts = _load_accounts()
        acc_id = str(uuid.uuid4())
        new_acc = {
            "id": acc_id,
            "platform": platform,
            "user_name": user_name,
            "cookie_file": cookie_filename,
            "status": 1,
        }
        accounts.append(new_acc)
        _save_accounts(accounts)
        return AccountResponse(**new_acc)

    def delete_account(self, account_id: str) -> bool:
        accounts = _load_accounts()
        filtered = [a for a in accounts if a["id"] != account_id]
        if len(filtered) == len(accounts):
            raise NotFoundException(f"账号不存在: {account_id}")
        _save_accounts(filtered)
        return True

    def get_account(self, account_id: str) -> dict:
        accounts = _load_accounts()
        for a in accounts:
            if a["id"] == account_id:
                return a
        raise NotFoundException(f"账号不存在: {account_id}")
    
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

    def set_account_status(self, account_id: str, status_val: int) -> None:
        accounts = _load_accounts()
        for a in accounts:
            if a["id"] == account_id:
                a["status"] = status_val
                _save_accounts(accounts)
                return
        raise NotFoundException(f"账号不存在: {account_id}")

    def check_cookie_valid(self, platform: str, account_id: str) -> bool:
        """
        使用各平台既有 cookie_auth 校验 Playwright storage_state 是否仍可访问创作者页。
        在线程中通过 asyncio.run 执行，供 publish 前置校验。
        """
        _ensure_uploader_dirs()
        acc = self.get_account(account_id)
        if acc.get("platform") != platform:
            return False
        cookie_path = self._get_cookie_file_path(acc)
        if not cookie_path.is_file():
            return False
        abs_path = str(cookie_path.resolve())

        async def _validate() -> bool:
            if platform == "douyin":
                return await douyin_cookie_auth(abs_path)
            if platform == "tencent":
                return await tencent_cookie_auth(abs_path)
            if platform == "xhs":
                return await xhs_cookie_auth(abs_path)
            return False

        return asyncio.run(_validate())

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

    def _run_publish_sync(
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
        """同步执行发布（在线程中运行 asyncio）"""
        from datetime import datetime
        
        # 解析定时发布时间
        publish_datetime = 0
        if publish_date:
            try:
                publish_datetime = datetime.fromisoformat(publish_date.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                logger.warning(f"Invalid publish_date format: {publish_date}, using immediate publish")
                publish_datetime = 0
        
        async def _do():
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

        asyncio.run(_do())

    def publish(
        self,
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
        acc = self.get_account(account_id)
        cookie_file = self._get_cookie_file_path(acc)

        video_path = _resolve_publish_video_path(video_id)

        self._run_publish_sync(
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
