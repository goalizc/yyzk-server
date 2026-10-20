"""工单业务：提交（含首条流转日志）与状态流转规则。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.models import Fault, Part, Product, Ticket, TicketStatusLog, User
from app.schemas.ticket import TicketSubmit, TicketUpdate
from app.services.ticket_no import next_ticket_no

# 契约 §5 的状态机：closed 为终态，resolved 不能回到 open
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"processing", "closed"},
    "processing": {"resolved", "closed"},
    "resolved": {"closed"},
    "closed": set(),
}

_MAX_ATTEMPTS = 3


def _validate_context(db: Session, payload: TicketSubmit) -> None:
    """选填的产品/零件/故障：传了就必须存在，且零件要属于产品。"""
    if payload.product_id is not None and db.get(Product, payload.product_id) is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)
    if payload.part_id is not None:
        part = db.get(Part, payload.part_id)
        if part is None:
            raise BusinessError("NOT_FOUND", "零件不存在", 404)
        if payload.product_id is not None and part.product_id != payload.product_id:
            raise BusinessError("PART_PRODUCT_MISMATCH", "零件不属于所选产品", 400)
    if payload.fault_id is not None and db.get(Fault, payload.fault_id) is None:
        raise BusinessError("NOT_FOUND", "故障不存在", 404)


def create_ticket(db: Session, payload: TicketSubmit) -> Ticket:
    _validate_context(db, payload)

    for _ in range(_MAX_ATTEMPTS):
        try:
            ticket = Ticket(
                ticket_no=next_ticket_no(db),
                product_id=payload.product_id,
                part_id=payload.part_id,
                fault_id=payload.fault_id,
                contact=payload.contact.strip(),
                contact_name=(payload.contact_name or "").strip() or None,
                description=payload.description.strip(),
                need_on_site=payload.need_on_site,
                status="open",
            )
            db.add(ticket)
            db.flush()
            # 首条流转日志：少了它详情页的“流转历史”会缺第一行
            db.add(
                TicketStatusLog(
                    ticket_id=ticket.id,
                    from_status=None,
                    to_status="open",
                    operator_id=None,
                    remark=None,
                )
            )
            db.commit()
            db.refresh(ticket)
            return ticket
        except IntegrityError:
            # 工单号撞车（并发下唯一键兜底），回滚后重新取号
            db.rollback()
            continue

    raise BusinessError("INTERNAL_ERROR", "工单号生成失败，请稍后重试", 500)


def apply_update(db: Session, ticket: Ticket, payload: TicketUpdate, operator: User) -> Ticket:
    """应用状态/备注/处理人变更；状态变化时写流转日志。"""
    data = payload.model_dump(exclude_unset=True)
    # 全传 null 视同没改（否则会静默只改处理人）
    if not any(value is not None for value in data.values()):
        raise BusinessError("VALIDATION_ERROR", "请至少修改一项", 400)

    new_status = data.get("status")
    remark = data.get("remark")
    remark_text = (remark or "").strip() or None

    if new_status is not None and new_status != ticket.status:
        if not remark_text:
            raise BusinessError("VALIDATION_ERROR", "变更状态时必须填写备注", 400)
        allowed = ALLOWED_TRANSITIONS.get(ticket.status, set())
        if new_status not in allowed:
            raise BusinessError(
                "TICKET_STATUS_INVALID", f"不能从 {ticket.status} 直接流转到 {new_status}", 400
            )
        db.add(
            TicketStatusLog(
                ticket_id=ticket.id,
                from_status=ticket.status,
                to_status=new_status,
                operator_id=operator.id,
                remark=remark_text,
            )
        )
        ticket.status = new_status

    if remark is not None:
        ticket.remark = remark_text
    if data.get("need_on_site") is not None:
        ticket.need_on_site = data["need_on_site"]

    # 处理人规则（产品确认）：
    # 1) 显式传 assignee_id → 转派给该人（视为确认认领）
    # 2) 未传且当前无处理人 → 由操作人认领（首次处理即归属）
    # 3) 未传但已有人处理 → 保持原处理人，不静默抢占
    explicit_assignee = data.get("assignee_id")
    if explicit_assignee is not None:
        ticket.assignee_id = explicit_assignee
    elif ticket.assignee_id is None:
        ticket.assignee_id = operator.id

    ticket.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(ticket)
    return ticket
