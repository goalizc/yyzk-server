"""操作审计 schema（契约 §6 新增）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.schemas.common import AppDateTime


class AuditLogItem(BaseModel):
    """列表项：不带 detail（可能较大），点开详情再看。"""

    id: int
    created_at: AppDateTime
    username: str
    action: str
    target_type: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    method: str
    path: str
    status: int
    result: str
    ip: str | None = None
    request_id: str | None = None


class AuditLogDetail(AuditLogItem):
    user_id: int | None = None
    error_code: str | None = None
    user_agent: str | None = None
    detail: dict[str, Any] = {}


class AuditLogPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AuditLogItem]


class ActorSummary(BaseModel):
    """按人聚合：谁操作最多、谁在失败、谁从多个 IP 登录（账号外传的强信号）。"""

    user_id: int | None = None
    username: str
    total: int
    failures: int
    distinct_ips: int
    last_at: AppDateTime


class AuditSummary(BaseModel):
    period_days: int
    total: int
    failures: int
    actors: list[ActorSummary]
