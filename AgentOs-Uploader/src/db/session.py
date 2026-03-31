# -*- coding: utf-8 -*-
"""
SQLAlchemy 异步 Session 工厂
"""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from .models import Base

# 数据库文件路径：优先使用环境变量，否则写入 storage 目录
_default_db = Path(__file__).parent.parent.parent / "storage" / "uploader.db"
DATABASE_URL = os.getenv(
    "UPLOADER_DB_URL",
    f"sqlite+aiosqlite:///{_default_db}",
)

engine = create_async_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,   # SQLite 单连接池，避免 "database is locked"
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
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """FastAPI 依赖项用法：async with get_session() as session: ..."""
    async with AsyncSessionLocal() as session:
        yield session
