"""公开接口：客户侧产品/零件/故障与反馈（契约 §2、§3、§4）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import BusinessError
from app.database import get_db
from app.models import Fault, Part, Product, QueryLog
from app.schemas.common import ErrorBody
from app.schemas.fault import (
    FaultDetail,
    FaultListItem,
    FeedbackRequest,
    FeedbackResponse,
    QueryLogCreate,
    QueryLogCreated,
)
from app.schemas.part import PartPublic
from app.schemas.product import ProductPublic
from app.schemas.ticket import TicketCreated, TicketSubmit
from app.services.query_log import build_log
from app.utils.search import LIKE_ESCAPE, like_pattern
from app.services.ticket import create_ticket

router = APIRouter()


@router.get(
    "/products",
    response_model=list[ProductPublic],
    summary="已上架产品列表",
    description="只返回 is_active=true，按 sort_order 升序；产品量在百级以内，无分页。",
)
def list_products(db: Session = Depends(get_db)) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.is_active.is_(True))
        .options(selectinload(Product.line))
        .order_by(Product.sort_order, Product.id)
    )
    return list(db.scalars(stmt))


@router.get(
    "/products/{product_id}/parts",
    response_model=list[PartPublic],
    summary="某产品下的零件（级联下拉）",
    responses={404: {"model": ErrorBody, "description": "产品不存在"}},
)
def list_product_parts(product_id: int, db: Session = Depends(get_db)) -> list[Part]:
    if db.get(Product, product_id) is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)

    stmt = (
        select(Part)
        .where(Part.product_id == product_id)
        .order_by(Part.group_name, Part.sort_order, Part.id)
    )
    return list(db.scalars(stmt))


# ---------------------------------------------------------------- 故障


@router.get(
    "/faults",
    response_model=list[FaultListItem],
    summary="客户侧故障列表",
    description="仅返回已发布故障，按 view_count 降序；关键词匹配标题与现象，无结果返回空数组。",
)
def list_faults(
    product_id: int = Query(..., description="产品 ID"),
    part_id: int = Query(..., description="零件 ID"),
    q: str | None = Query(None, max_length=50, description="关键词"),
    db: Session = Depends(get_db),
) -> list[Fault]:
    stmt = select(Fault).where(
        Fault.product_id == product_id,
        Fault.part_id == part_id,
        Fault.is_published.is_(True),
    )
    if q and q.strip():
        lowered = like_pattern(q.lower())
        stmt = stmt.where(
            or_(
                func.lower(Fault.title).like(lowered, escape=LIKE_ESCAPE),
                func.lower(func.coalesce(Fault.symptom, "")).like(lowered, escape=LIKE_ESCAPE),
            )
        )
    stmt = stmt.order_by(Fault.view_count.desc(), Fault.id.desc())
    return list(db.scalars(stmt))


@router.get(
    "/faults/{fault_id}",
    response_model=FaultDetail,
    summary="故障详情（含浏览计数与日志写入）",
    responses={404: {"model": ErrorBody, "description": "故障不存在或未发布"}},
)
def get_fault(
    fault_id: int,
    request: Request,
    q: str | None = Query(None, max_length=100, description="本次检索词，写入日志"),
    db: Session = Depends(get_db),
) -> FaultDetail:
    row = db.execute(
        select(Fault, Product.name, Part.name)
        .join(Product, Fault.product_id == Product.id)
        .join(Part, Fault.part_id == Part.id)
        .where(Fault.id == fault_id, Fault.is_published.is_(True))
    ).first()
    if row is None:
        raise BusinessError("NOT_FOUND", "故障不存在", 404)

    fault, product_name, part_name = row

    # 计数用原子自增，避免并发下读改写丢更新
    db.execute(
        update(Fault).where(Fault.id == fault_id).values(view_count=Fault.view_count + 1)
    )
    log = build_log(
        request,
        hit=True,
        product_id=fault.product_id,
        part_id=fault.part_id,
        fault_id=fault_id,
        raw_query=(q.strip() or None) if q else None,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    db.refresh(fault)

    return FaultDetail(
        id=fault.id,
        product_id=fault.product_id,
        part_id=fault.part_id,
        product_name=product_name,
        part_name=part_name,
        title=fault.title,
        symptom=fault.symptom,
        root_cause=fault.root_cause,
        solution_steps=fault.solution_steps or [],
        required_tools=fault.required_tools,
        needs_professional=fault.needs_professional,
        attachment_urls=fault.attachment_urls or [],
        view_count=fault.view_count,
        resolved_count=fault.resolved_count,
        query_log_id=log.id,
    )


@router.post(
    "/faults/{fault_id}/feedback",
    response_model=FeedbackResponse,
    summary="反馈是否解决（幂等）",
    responses={
        400: {"model": ErrorBody, "description": "query_log_id 与故障不匹配"},
        404: {"model": ErrorBody, "description": "故障不存在"},
    },
)
def feedback(
    fault_id: int,
    payload: FeedbackRequest,
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    if db.get(Fault, fault_id) is None:
        raise BusinessError("NOT_FOUND", "故障不存在", 404)

    log = db.get(QueryLog, payload.query_log_id)
    if log is None or log.fault_id != fault_id:
        raise BusinessError("QUERY_LOG_MISMATCH", "反馈的日志与故障不匹配", 400)

    # 只有状态真的变了才计数，重复点击/重试不会重复加减
    changed = db.execute(
        update(QueryLog)
        .where(
            QueryLog.id == log.id,
            QueryLog.resolved.is_distinct_from(payload.resolved),
        )
        .values(resolved=payload.resolved)
    )
    if changed.rowcount == 1:
        if payload.resolved:
            db.execute(
                update(Fault)
                .where(Fault.id == fault_id)
                .values(resolved_count=Fault.resolved_count + 1)
            )
        else:
            db.execute(
                update(Fault)
                .where(Fault.id == fault_id)
                .values(
                    resolved_count=case(
                        (Fault.resolved_count > 0, Fault.resolved_count - 1), else_=0
                    )
                )
            )
    db.commit()
    return FeedbackResponse()


@router.post(
    "/query-logs",
    status_code=201,
    response_model=QueryLogCreated,
    summary="上报一次未命中检索",
    responses={404: {"model": ErrorBody, "description": "产品或零件不存在"}},
)
def create_query_log(
    payload: QueryLogCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> QueryLogCreated:
    if db.get(Product, payload.product_id) is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)
    part = db.get(Part, payload.part_id)
    if part is None:
        raise BusinessError("NOT_FOUND", "零件不存在", 404)
    if part.product_id != payload.product_id:
        # 组合错配会污染未命中统计的分组口径，直接拒绝
        raise BusinessError("PART_PRODUCT_MISMATCH", "零件不属于所选产品", 400)

    log = build_log(
        request,
        hit=False,
        product_id=payload.product_id,
        part_id=payload.part_id,
        raw_query=payload.raw_query,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return QueryLogCreated(id=log.id)


# ---------------------------------------------------------------- 工单


@router.post(
    "/tickets",
    status_code=201,
    response_model=TicketCreated,
    summary="客户提交工单",
    responses={
        400: {"model": ErrorBody, "description": "联系方式/描述不合法"},
        404: {"model": ErrorBody, "description": "关联的产品、零件或故障不存在"},
    },
)
def submit_ticket(payload: TicketSubmit, db: Session = Depends(get_db)) -> TicketCreated:
    # 契约 §5 明确这两项返回 400（不是 Pydantic 的 422），故在路由层校验
    contact = payload.contact.strip()
    if not 5 <= len(contact) <= 100:
        raise BusinessError("VALIDATION_ERROR", "请填写联系方式", 400)
    description = payload.description.strip()
    if not 5 <= len(description) <= 2000:
        raise BusinessError("VALIDATION_ERROR", "请描述故障情况（至少 5 个字）", 400)

    ticket = create_ticket(db, payload)
    return TicketCreated(ticket_no=ticket.ticket_no, created_at=ticket.created_at)
