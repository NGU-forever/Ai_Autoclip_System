# -*- coding: utf-8 -*-
"""
Celery 应用实例
使用项目已有的 Redis 服务作为 Broker 和 Result Backend。

特殊说明：
- task_acks_late=True: Worker 处理完才回执，崩溃时任务会重入队列
- task_reject_on_worker_lost=True: Worker 失联时拒绝任务（而不是 ack）
- worker_prefetch_multiplier=1: 每个 Worker 一次只预取 1 个任务，防止 Playwright 资源耗尽
- --pool=solo: 与 asyncio 兼容，Playwright 依赖 asyncio 事件循环，prefork 会 fork 进程破坏 loop
"""

import logging

from celery import Celery
from src.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "uploader",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.tasks.publish"],
)

celery_app.conf.update(
    # 序列化
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # 可靠性配置
    task_acks_late=True,              # 任务完成后才 ack，Worker 崩溃时重入队列
    task_reject_on_worker_lost=True,  # Worker 失联时拒绝任务（重入队列）
    worker_prefetch_multiplier=1,     # 每个 Worker 同一时间只处理 1 个 Playwright 任务
    task_track_started=True,          # 追踪 STARTED 状态
    # 结果过期时间（24 小时后自动清理 Redis 中的任务结果）
    result_expires=86400,
    # 时区
    timezone="Asia/Shanghai",
    enable_utc=True,
)

logger.info(
    "Celery app initialized. Broker: %s",
    settings.redis_url.split("@")[-1] if "@" in settings.redis_url else settings.redis_url,
)
