"""工单 schema（契约 §5）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import AppDateTime

TicketStatus = Literal["open", "processing", "resolved", "closed"]


class ProductBrief(BaseModel):
    id: int
    name: str
    model: str


class PartBrief(BaseModel):
    id: int
    name: str


class FaultBrief(BaseModel):
    id: int
    title: str
    needs_professional: bool


class TicketSubmit(BaseModel):
    """客户提交工单。contact / description 的长度在路由里校验（契约要求 400 而非 422）。"""

    product_id: int | None = None
    part_id: int | None = None
    fault_id: int | None = None
    contact: str = Field(examples=["13800138000"])
    contact_name: str | None = Field(default=None, max_length=50)
    description: str = Field(examples=["按步骤试了还是不行，电池刚换过"])
    need_on_site: bool


class TicketCreated(BaseModel):
    ticket_no: str
    created_at: AppDateTime


class TicketListItem(BaseModel):
    id: int
    ticket_no: str
    product_name: str | None = None
    product_model: str | None = None
    part_name: str | None = None
    fault_title: str | None = None
    contact: str  # 列表脱敏
    contact_name: str | None = None
    need_on_site: bool
    status: TicketStatus
    assignee_name: str | None = None
    created_at: AppDateTime
    updated_at: AppDateTime


class TicketPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[TicketListItem]


class TicketHistoryItem(BaseModel):
    from_status: str | None = None
    to_status: str
    operator_name: str | None = None
    remark: str | None = None
    created_at: AppDateTime


class TicketDetail(BaseModel):
    id: int
    ticket_no: str
    status: TicketStatus
    contact: str  # 详情返回完整联系方式
    contact_name: str | None = None
    need_on_site: bool
    description: str
    remark: str | None = None
    assignee_id: int | None = None
    assignee_name: str | None = None
    product: ProductBrief | None = None
    part: PartBrief | None = None
    fault: FaultBrief | None = None
    created_at: AppDateTime
    updated_at: AppDateTime
    history: list[TicketHistoryItem] = []


class TicketUpdate(BaseModel):
    status: TicketStatus | None = None
    remark: str | None = Field(default=None, max_length=2000)
    assignee_id: int | None = None
    need_on_site: bool | None = None
