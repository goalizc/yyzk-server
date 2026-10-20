"""分页查询（契约 §0.1：列表统一 {total, page, page_size, items}）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def paginate(db: Session, stmt: Select, page: int, page_size: int) -> tuple[int, list[Any]]:
    """返回 (总数, 当前页行)。总数用子查询统计，避免把 join 的列也算进去。"""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return total, list(rows)
