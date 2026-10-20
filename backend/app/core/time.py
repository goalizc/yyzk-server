"""时间处理：统一按应用时区输出。

SQLite（单测）读出来的是 naive datetime，PostgreSQL 是带时区的；
对外一律输出 `+08:00`，与契约一致。
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import get_settings


def to_app_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(get_settings().timezone)


def to_db_datetime(db, value: datetime) -> datetime:
    """比较用的时间边界：SQLite 不保存时区，统一成 UTC naive；PostgreSQL 保持带时区。"""
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "sqlite":
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
