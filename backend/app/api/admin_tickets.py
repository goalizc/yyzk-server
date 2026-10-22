"""后台工单：列表、详情、状态流转（契约 §5）。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import BusinessError
from app.core.permissions import TICKET_READ, TICKET_WRITE, require
from app.core.time import to_db_datetime
from app.database import get_db
from app.models import Fault, Part, Product, Ticket, TicketStatusLog, User
from app.schemas.common import ErrorBody
from app.schemas.ticket import (
    FaultBrief,
    PartBrief,
    ProductBrief,
    TicketDetail,
    TicketHistoryItem,
    TicketListItem,
    TicketPage,
    TicketUpdate,
)
from app.services.pagination import paginate
from app.services.ticket import apply_update
from app.utils.search import LIKE_ESCAPE, like_pattern

router = APIRouter()


def mask_contact(contact: str) -> str:
    """列表脱敏：保留前 3 位与后 4 位（契约 §5）。"""
    if len(contact) <= 7:
        return contact[:1] + "*" * (len(contact) - 1)
    return f"{contact[:3]}****{contact[-4:]}"


def _detail(db: Session, ticket: Ticket) -> TicketDetail:
    product = db.get(Product, ticket.product_id) if ticket.product_id else None
    part = db.get(Part, ticket.part_id) if ticket.part_id else None
    fault = db.get(Fault, ticket.fault_id) if ticket.fault_id else None
    assignee = db.get(User, ticket.assignee_id) if ticket.assignee_id else None

    rows = db.execute(
        select(TicketStatusLog, User.real_name)
        .outerjoin(User, TicketStatusLog.operator_id == User.id)
        .where(TicketStatusLog.ticket_id == ticket.id)
        .order_by(TicketStatusLog.created_at, TicketStatusLog.id)
    ).all()

    return TicketDetail(
        id=ticket.id,
        ticket_no=ticket.ticket_no,
        status=ticket.status,
        contact=ticket.contact,
        contact_name=ticket.contact_name,
        need_on_site=ticket.need_on_site,
        description=ticket.description,
        remark=ticket.remark,
        assignee_id=ticket.assignee_id,
        assignee_name=assignee.real_name if assignee else None,
        product=ProductBrief(id=product.id, name=product.name, model=product.model)
        if product
        else None,
        part=PartBrief(id=part.id, name=part.name) if part else None,
        fault=FaultBrief(id=fault.id, title=fault.title, needs_professional=fault.needs_professional)
        if fault
        else None,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        history=[
            TicketHistoryItem(
                from_status=log.from_status,
                to_status=log.to_status,
                operator_name=operator_name,
                remark=log.remark,
                created_at=log.created_at,
            )
            for log, operator_name in rows
        ],
    )


@router.get("/tickets", response_model=TicketPage, summary="工单列表（联系方式脱敏）")
def list_tickets(
    status: str | None = Query(None, pattern="^(open|processing|resolved|closed)$"),
    start_date: date | None = Query(None, description="创建时间起（含），YYYY-MM-DD"),
    end_date: date | None = Query(None, description="创建时间止（含当日），YYYY-MM-DD"),
    keyword: str | None = Query(None, max_length=100, description="匹配工单号或联系方式"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(TICKET_READ)),
) -> TicketPage:
    stmt = (
        select(Ticket, Product.name, Product.model, Part.name, Fault.title, User.real_name)
        .outerjoin(Product, Ticket.product_id == Product.id)
        .outerjoin(Part, Ticket.part_id == Part.id)
        .outerjoin(Fault, Ticket.fault_id == Fault.id)
        .outerjoin(User, Ticket.assignee_id == User.id)
    )

    if status is not None:
        stmt = stmt.where(Ticket.status == status)
    if start_date is not None or end_date is not None:
        tz = get_settings().timezone
        if start_date is not None:
            stmt = stmt.where(
                Ticket.created_at
                >= to_db_datetime(db, datetime.combine(start_date, time.min, tzinfo=tz))
            )
        if end_date is not None:
            # 半开区间：< 次日 00:00，避免漏掉 23:59:59.001–.999
            stmt = stmt.where(
                Ticket.created_at
                < to_db_datetime(
                    db, datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
                )
            )
    if keyword and keyword.strip():
        lowered = like_pattern(keyword)
        stmt = stmt.where(
            or_(
                Ticket.ticket_no.like(lowered, escape=LIKE_ESCAPE),
                Ticket.contact.like(lowered, escape=LIKE_ESCAPE),
            )
        )

    stmt = stmt.order_by(Ticket.created_at.desc(), Ticket.id.desc())
    total, rows = paginate(db, stmt, page, page_size)

    return TicketPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            TicketListItem(
                id=ticket.id,
                ticket_no=ticket.ticket_no,
                product_name=product_name,
                product_model=product_model,
                part_name=part_name,
                fault_title=fault_title,
                contact=mask_contact(ticket.contact),
                contact_name=ticket.contact_name,
                need_on_site=ticket.need_on_site,
                status=ticket.status,
                assignee_name=assignee_name,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
            )
            for ticket, product_name, product_model, part_name, fault_title, assignee_name in rows
        ],
    )


@router.get(
    "/tickets/{ticket_id}",
    response_model=TicketDetail,
    summary="工单详情（含完整联系方式与流转历史）",
    responses={404: {"model": ErrorBody, "description": "工单不存在"}},
)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(TICKET_READ)),
) -> TicketDetail:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise BusinessError("NOT_FOUND", "工单不存在", 404)
    return _detail(db, ticket)


@router.put(
    "/tickets/{ticket_id}",
    response_model=TicketDetail,
    summary="更新状态/备注/处理人",
    responses={
        400: {"model": ErrorBody, "description": "状态流转非法或缺少备注"},
        404: {"model": ErrorBody, "description": "工单或处理人不存在"},
    },
)
def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require(TICKET_WRITE)),
) -> TicketDetail:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise BusinessError("NOT_FOUND", "工单不存在", 404)
    if payload.assignee_id is not None and db.get(User, payload.assignee_id) is None:
        raise BusinessError("NOT_FOUND", "处理人不存在", 404)

    apply_update(db, ticket, payload, user)
    return _detail(db, ticket)
