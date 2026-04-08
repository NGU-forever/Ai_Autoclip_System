# -*- coding: utf-8 -*-
"""
数据库模型定义
用 SQLAlchemy ORM 替代 accounts.json / uploader_tasks.json
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Boolean,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    """平台账号（替代 accounts.json）"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(32), nullable=False, index=True)   # douyin / tencent / xhs
    account_name = Column(String(128), nullable=False)
    cookie_file = Column(String(256), nullable=False)           # 相对 cookies 目录的文件名
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # 关联任务（便于查询某账号下所有任务）
    tasks = relationship("UploaderTask", back_populates="account", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "platform": self.platform,
            "account_name": self.account_name,
            "cookie_file": self.cookie_file,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UploaderTask(Base):
    """上传任务（替代 uploader_tasks.json）"""
    __tablename__ = "uploader_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(32), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    video_id = Column(String(512), nullable=False)
    video_path = Column(String(512), nullable=True)
    title = Column(String(256), nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)                          # JSON 字符串，例如 '["tag1","tag2"]'
    request_data = Column(Text, nullable=True)                  # JSON 字符串，保存原始请求参数用于重试

    # 状态字段
    status = Column(String(32), nullable=False, default="pending", index=True)
    # pending / running / success / failed / cancelled
    error_msg = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # 时间字段
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    # 关联账号
    account = relationship("Account", back_populates="tasks")

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id,
            "platform": self.platform,
            "account_id": self.account_id,
            "video_id": self.video_id,
            "video_path": self.video_path,
            "title": self.title,
            "description": self.description,
            "tags": json.loads(self.tags) if self.tags else [],
            "request_data": json.loads(self.request_data) if self.request_data else {},
            "status": self.status,
            "error_msg": self.error_msg,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
