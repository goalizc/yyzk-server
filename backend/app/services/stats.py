"""统计口径（契约 §6）。

三条铁律，改之前先看契约：
1. 解决率分母是 `hit=true` 的条数，不是 `fault_id IS NOT NULL`
   —— 故障被删后 `fault_id` 会置 NULL，分母会凭空缩水、解决率虚高甚至超 100%；
2. 不使用 `faults.resolved_count / view_count` 做看板口径（历史累计，与时间筛选冲突）；
3. `open_tickets` 是当前积压，不随 `days` 变化。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Fault, Part, Product, QueryLog, Ticket

MISSED_EMPTY_LABEL = "(未输入关键词)"


def _since(days: int) -> datetime | None:
    """days=0 表示全部（不加时间条件）。"""
    if days <= 0:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def overview(db: Session, days: int) -> dict[str, Any]:
    since = _since(days)
    log_filters = [] if since is None else [QueryLog.created_at >= since]

    total, views, resolved, missed = db.execute(
        select(
            func.count(QueryLog.id),
            func.count(case((QueryLog.hit.is_(True), 1))),
            func.count(case((QueryLog.resolved.is_(True), 1))),
            func.count(case((QueryLog.hit.is_(False), 1))),
        ).where(*log_filters)
    ).one()

    ticket_filters = [] if since is None else [Ticket.created_at >= since]
    total_tickets = db.scalar(select(func.count(Ticket.id)).where(*ticket_filters)) or 0
    # 当前积压：不带时间条件
    open_tickets = (
        db.scalar(
            select(func.count(Ticket.id)).where(Ticket.status.in_(("open", "processing")))
        )
        or 0
    )

    return {
        "period_days": days,
        "total_queries": total,
        "view_queries": views,
        "resolved_queries": resolved,
        "resolve_rate": round(resolved / views, 3) if views else None,
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "missed_queries": missed,
    }


def top_faults(db: Session, days: int, limit: int) -> list[dict[str, Any]]:
    since = _since(days)
    filters = [QueryLog.fault_id.is_not(None)]
    if since is not None:
        filters.append(QueryLog.created_at >= since)

    views = (
        select(
            QueryLog.fault_id.label("fault_id"),
            func.count(QueryLog.id).label("period_views"),
        )
        .where(*filters)
        .group_by(QueryLog.fault_id)
        .subquery()
    )

    rows = db.execute(
        select(Fault, Product.name, Part.name, views.c.period_views)
        .select_from(Fault)
        .join(views, views.c.fault_id == Fault.id)
        .join(Product, Fault.product_id == Product.id)
        .join(Part, Fault.part_id == Part.id)
        .order_by(views.c.period_views.desc(), Fault.id)
        .limit(limit)
    ).all()

    return [
        {
            "fault_id": fault.id,
            "title": fault.title,
            "product_name": product_name,
            "part_name": part_name,
            "view_count": fault.view_count,
            "resolved_count": fault.resolved_count,
            "period_views": period_views,
        }
        for fault, product_name, part_name, period_views in rows
    ]


def missed(db: Session, days: int, limit: int) -> list[dict[str, Any]]:
    since = _since(days)
    filters = [QueryLog.hit.is_(False)]
    if since is not None:
        filters.append(QueryLog.created_at >= since)

    # 归一化：去首尾空格 + 转小写；空值统一落进 (未输入关键词)
    key = func.coalesce(
        func.nullif(func.lower(func.trim(QueryLog.raw_query)), ""), MISSED_EMPTY_LABEL
    )

    grouped = (
        select(
            key.label("raw_query"),
            func.count(QueryLog.id).label("cnt"),
            func.max(QueryLog.id).label("sample_id"),
            func.max(QueryLog.created_at).label("last_seen_at"),
        )
        .where(*filters)
        .group_by(key)
        .subquery()
    )

    rows = db.execute(
        select(
            grouped.c.raw_query,
            grouped.c.cnt,
            grouped.c.last_seen_at,
            Product.name,
            Part.name,
        )
        .select_from(grouped)
        # 取该分组里最新一条作为样例，顺带带出产品/零件名
        .join(QueryLog, QueryLog.id == grouped.c.sample_id)
        .outerjoin(Product, QueryLog.product_id == Product.id)
        .outerjoin(Part, QueryLog.part_id == Part.id)
        .order_by(grouped.c.cnt.desc(), grouped.c.raw_query)
        .limit(limit)
    ).all()

    return [
        {
            "raw_query": raw_query,
            "count": count,
            "sample_product_name": product_name,
            "sample_part_name": part_name,
            "last_seen_at": last_seen_at,
        }
        for raw_query, count, last_seen_at, product_name, part_name in rows
    ]
