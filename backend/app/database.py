"""数据库连接与会话。

连接池容量对应系统架构设计.md §7 的 100 并发基线：
pool_size=5 + max_overflow=10，每个 worker 一套池，2 worker 共 30 连接。
"""

from __future__ import annotations

from collections.abc import Generator
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def _engine_options(url: str) -> dict:
    """SQLite 只在单测里用，不传 PostgreSQL 专属的连接池参数。"""
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}

    settings = get_settings()
    return {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
        "pool_pre_ping": True,
        "echo": settings.db_echo,
    }


_engine: Engine | None = None
_engine_lock = Lock()
_session_factory = sessionmaker(autoflush=False, expire_on_commit=False)


def get_engine() -> Engine:
    """进程内单例；首次调用时才建池，避免导入即连库。

    用双重检查锁兜住并发：多线程同时首次调用时不至于建出两个连接池。
    """
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                settings = get_settings()
                _engine = create_engine(
                    settings.database_url, **_engine_options(settings.database_url)
                )
    return _engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级会话。"""
    session = _session_factory(bind=get_engine())
    try:
        yield session
    finally:
        session.close()
