# -*- coding: utf-8 -*-
"""
发布视频 Celery Task

设计要点：
- max_retries=0: 发布任务不自动重试（用户手动触发重试，避免重复发布）
- bind=True: 可访问 self.request.id 获取 Celery task ID（与内部 task_id 区分）
- 业务逻辑完全委托给 UploaderService.execute_publish_task，无重复代码
"""

import logging

from src.tasks.celery_app import celery_app
from src.upload.service import UploaderService

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.publish_video",
    max_retries=0,
    acks_late=True,
)
def publish_video_task(
    self,
    task_id: str,
    platform: str,
    account_id: str,
    video_id: str,
    title: str,
    tags: list,
    category: str | None = None,
    is_draft: bool = False,
    thumbnail_path: str | None = None,
    product_link: str | None = None,
    product_title: str | None = None,
    desc: str | None = None,
    cover_path: str | None = None,
    is_private: bool = False,
    publish_date: str | None = None,
    short_title: str | None = None,
    declare_original: bool = False,
):
    """
    持久化发布任务。
    由 Celery Worker 在独立进程中执行，确保 API 容器重启不影响任务执行。
    """
    logger.info(
        "Celery Worker 开始执行发布任务: task_id=%s, platform=%s, celery_task_id=%s",
        task_id, platform, self.request.id,
    )
    service = UploaderService()
    # 直接复用现有业务逻辑，无需任何改动
    service.execute_publish_task(
        task_id=task_id,
        platform=platform,
        account_id=account_id,
        video_id=video_id,
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
    logger.info("Celery Worker 完成发布任务: task_id=%s", task_id)
