"""工单可见范围。数据范围只作用于工单，知识库对外公开不限制。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.permissions import ALL, TICKET_WRITE, data_scope, effective_permissions
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


def assignable_users(db: Session, product_id: int | None) -> list[User]:
    """可改派的处理人：启用、有 ticket:write，且能看到指定产品。"""
    candidates = db.scalars(
        select(User).where(User.is_active.is_(True)).order_by(User.real_name, User.id)
    ).all()
    result: list[User] = []
    for user in candidates:
        if TICKET_WRITE not in effective_permissions(db, user):
            continue
        product_ids = visible_product_ids(db, user)
        if product_ids is None:
            result.append(user)
        elif product_id is not None and product_id in product_ids:
            result.append(user)
    return result


def ensure_assignable(db: Session, ticket: Ticket, assignee_id: int) -> User:
    """校验目标处理人：存在、启用、有 ticket:write、且可见工单所属产品。"""
    assignee = db.get(User, assignee_id)
    if assignee is None:
        raise BusinessError("NOT_FOUND", "处理人不存在", 404)
    if not assignee.is_active:
        raise BusinessError("ASSIGNEE_DISABLED", "该账号已停用，不能作为处理人", 400)
    if TICKET_WRITE not in effective_permissions(db, assignee):
        raise BusinessError("ASSIGNEE_NO_PERMISSION", "该账号没有处理工单的权限", 400)

    product_ids = visible_product_ids(db, assignee)
    if product_ids is not None:
        if ticket.product_id is None or ticket.product_id not in product_ids:
            raise BusinessError("ASSIGNEE_OUT_OF_SCOPE", "该账号看不到此工单所属产品线", 400)
    return assignee
