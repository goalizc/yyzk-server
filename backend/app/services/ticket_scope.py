"""工单可见范围。数据范围只作用于工单，知识库对外公开不限制。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.permissions import ALL, data_scope
from app.models import Product, Ticket, User, UserProductLine


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def visible_product_ids(db: Session, user: User) -> set[int] | None:
    """None 表示不受限；空集合表示一条也看不到。"""
    if data_scope(user) == ALL:
        return None

    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(UserProductLine.line_id, UserProductLine.expires_at).where(
            UserProductLine.user_id == user.id
        )
    ).all()
    line_ids = [
        line_id
        for line_id, expires_at in rows
        if expires_at is None or _as_utc(expires_at) > now
    ]
    if not line_ids:
        return set()

    return set(
        db.scalars(select(Product.id).where(Product.line_id.in_(line_ids))).all()
    )


def apply_ticket_scope(stmt, db: Session, user: User):
    product_ids = visible_product_ids(db, user)
    if product_ids is None:
        return stmt
    return stmt.where(Ticket.product_id.in_(product_ids))


def ensure_ticket_visible(db: Session, user: User, ticket: Ticket) -> None:
    product_ids = visible_product_ids(db, user)
    if product_ids is None:
        return
    if ticket.product_id is None or ticket.product_id not in product_ids:
        raise BusinessError("PERMISSION_DENIED", "无权查看该工单", 403)
