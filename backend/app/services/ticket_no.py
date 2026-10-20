"""工单号生成：TK + yyyyMMdd + 4 位当日序号（契约 §5）。

并发要点：
- PostgreSQL 下先取**事务级**咨询锁，把同日取号串行化；
- 不能对聚合函数用 FOR UPDATE（PostgreSQL 直接报错），契约已注明；
- 唯一键冲突仍保留最多 3 次重试兜底。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import BusinessError
from app.models import Ticket

MAX_DAILY_SEQ = 9999


def next_ticket_no(db: Session) -> str:
    day = datetime.now(get_settings().timezone).strftime("%Y%m%d")
    prefix = f"TK{day}"

    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"ticket_no:{day}"},
        )

    seq = db.scalar(
        select(func.max(func.substr(Ticket.ticket_no, 11, 4).cast(Integer))).where(
            Ticket.ticket_no.like(f"{prefix}%")
        )
    )
    if (seq or 0) >= MAX_DAILY_SEQ:
        raise BusinessError("INTERNAL_ERROR", "当日工单号已达上限，请联系管理员", 500)
    return f"{prefix}{(seq or 0) + 1:04d}"
