"""查询日志（query_logs）。命中率与未命中统计的原始数据源。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="SET NULL")
    )
    part_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("parts.id", ondelete="SET NULL")
    )
    fault_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("faults.id", ondelete="SET NULL"), index=True
    )
    raw_query: Mapped[str | None] = mapped_column(String(100))
    hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved: Mapped[bool | None] = mapped_column(Boolean)
    ip: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
