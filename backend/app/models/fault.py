"""故障知识库（faults）。

`solution_steps` / `attachment_urls` 在 PostgreSQL 上是 JSONB；
用 with_variant 让 SQLite 单测也能建表，生产落库类型不变。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# 结构：[{"step":1,"text":"...","image_url":"..."}, ...]
SolutionSteps = JSON().with_variant(JSONB(), "postgresql")
# 结构：[{"name":"维修手册.pdf","url":"/uploads/x.pdf","size":102400}, ...]
AttachmentUrls = JSON().with_variant(JSONB(), "postgresql")


class Fault(Base):
    __tablename__ = "faults"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    part_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    symptom: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    solution_steps: Mapped[list] = mapped_column(SolutionSteps, nullable=False, default=list)
    required_tools: Mapped[str | None] = mapped_column(String(200))
    needs_professional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attachment_urls: Mapped[list] = mapped_column(AttachmentUrls, nullable=False, default=list)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    product: Mapped["Product"] = relationship()  # noqa: F821
    part: Mapped["Part"] = relationship()  # noqa: F821
