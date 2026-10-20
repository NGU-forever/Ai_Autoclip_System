# -*- coding: utf-8 -*-
"""
SQLAlchemy 异步 Session 工厂
"""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy import inspect, text

from .models import Base

from src.config import settings

# 数据库文件路径：优先使用环境变量，否则写入 storage 目录
# 注意：docker-compose 中常用的变量名为 DATABASE_URL
_default_db = Path("/app/storage/uploader.db")
DATABASE_URL = os.getenv(
    "UPLOADER_DB_URL",
    os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{_default_db}")
)

# 兼容处理：如果是 postgresql:// 需要替换为 postgresql+asyncpg:// 供 SQLAlchemy 异步引擎使用
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    # 仅 SQLite 需要 check_same_thread
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    poolclass=StaticPool if "sqlite" in DATABASE_URL else None,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def init_db() -> None:
    """在应用启动时创建所有表（幂等）"""
    async with engine.begin() as conn:
        # Additive migration: retain integer PKs, relationships and every existing row.
        # Serialize concurrent API startups before inspecting or changing the schema.
        if conn.dialect.name == "postgresql":
            await conn.execute(text("SELECT pg_advisory_xact_lock(724193851)"))
        elif conn.dialect.name == "sqlite":
            await conn.execute(text("BEGIN IMMEDIATE"))
        await conn.run_sync(Base.metadata.create_all)
        columns = await conn.run_sync(
            lambda sync: {c["name"] for c in inspect(sync).get_columns("uploader_tasks")}
        )
        if "task_id" not in columns:
            await conn.execute(text("ALTER TABLE uploader_tasks ADD COLUMN task_id VARCHAR(32)"))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_uploader_tasks_task_id ON uploader_tasks (task_id)"
        ))


async def get_session() -> AsyncSession:
    """FastAPI 依赖项用法：async with get_session() as session: ..."""
    async with AsyncSessionLocal() as session:
        yield session

