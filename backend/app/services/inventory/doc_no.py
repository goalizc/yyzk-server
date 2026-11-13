"""进销存单号生成：RK / CK / PD / PK + yyyyMMdd + 4 位当日序号（PRD §3.3）。

与 `backend/app/services/ticket_no.py` 同思路，但锁的粒度按「前缀 + 日期」拆分，
四种单据各自独立编号，互不阻塞。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import BusinessError
from app.models import InventoryDocument

MAX_DAILY_SEQ = 9999

_PREFIXES = {
    "inbound": "RK",
    "outbound": "CK",
    "adjust_in": "PD",
    "adjust_out": "PK",
}


def next_doc_no(db: Session, doc_type: str) -> str:
    code = _PREFIXES.get(doc_type)
    if code is None:
        raise BusinessError("VALIDATION_ERROR", "单据类型不合法", 400)

    day = datetime.now(get_settings().timezone).strftime("%Y%m%d")
    prefix = f"{code}{day}"

    # PostgreSQL 下用事务级咨询锁把同前缀同日取号串行化；
    # SQLite 单测不支持 pg_advisory_xact_lock，跳过（唯一键仍兜底）。
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"inventory_doc_no:{prefix}"},
        )

    # 2 位前缀 + 8 位日期，序号从第 11 位起 4 位
    seq = db.scalar(
        select(func.max(func.substr(InventoryDocument.doc_no, 11, 4).cast(Integer))).where(
            InventoryDocument.doc_no.like(f"{prefix}%")
        )
    )
    if (seq or 0) >= MAX_DAILY_SEQ:
        raise BusinessError("INTERNAL_ERROR", "当日单据号已达上限，请联系管理员", 500)
    return f"{prefix}{(seq or 0) + 1:04d}"
