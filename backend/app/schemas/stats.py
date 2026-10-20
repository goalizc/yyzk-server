"""统计看板 schema（契约 §6）。"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import AppDateTime


class StatsOverview(BaseModel):
    period_days: int
    total_queries: int
    view_queries: int
    resolved_queries: int
    resolve_rate: float | None  # 分母为 0 时 null
    total_tickets: int
    open_tickets: int  # 当前积压，不随窗口变化
    missed_queries: int


class TopFaultItem(BaseModel):
    fault_id: int
    title: str
    product_name: str
    part_name: str
    view_count: int  # 历史累计
    resolved_count: int
    period_views: int  # 窗口内浏览次数，排序依据


class MissedItem(BaseModel):
    raw_query: str
    count: int
    sample_product_name: str | None = None
    sample_part_name: str | None = None
    last_seen_at: AppDateTime
