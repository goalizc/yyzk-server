"""后台故障知识库 CRUD（契约 §4）。列表不带 solution_steps，回显不产生浏览计数。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.permissions import FAULT_READ, FAULT_WRITE, require
from app.database import get_db
from app.models import Fault, Part, Product, User
from app.schemas.common import ErrorBody, SuccessResponse
from app.schemas.fault import (
    FaultAdminDetail,
    FaultAdminItem,
    FaultCreate,
    FaultPage,
    FaultUpdate,
)
from app.services.pagination import paginate
from app.utils.search import LIKE_ESCAPE, like_pattern

router = APIRouter()

# 库中 NOT NULL，前端传 null 时忽略
_NOT_NULL = ("product_id", "part_id", "title", "needs_professional", "is_published")


def _ensure_product_part(db: Session, product_id: int, part_id: int) -> None:
    if db.get(Product, product_id) is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)
    part = db.get(Part, part_id)
    if part is None or part.product_id != product_id:
        raise BusinessError("PART_PRODUCT_MISMATCH", "零件不属于所选产品", 400)


def _to_admin_item(fault: Fault, product_name: str, part_name: str) -> FaultAdminItem:
    return FaultAdminItem(
        id=fault.id,
        product_id=fault.product_id,
        product_name=product_name,
        part_id=fault.part_id,
        part_name=part_name,
        title=fault.title,
        symptom=fault.symptom,
        needs_professional=fault.needs_professional,
        is_published=fault.is_published,
        view_count=fault.view_count,
        resolved_count=fault.resolved_count,
        attachment_count=len(fault.attachment_urls or []),
        created_at=fault.created_at,
        updated_at=fault.updated_at,
    )


def _to_admin_detail(fault: Fault) -> FaultAdminDetail:
    return FaultAdminDetail(
        id=fault.id,
        product_id=fault.product_id,
        part_id=fault.part_id,
        title=fault.title,
        symptom=fault.symptom,
        root_cause=fault.root_cause,
        solution_steps=fault.solution_steps or [],
        required_tools=fault.required_tools,
        needs_professional=fault.needs_professional,
        attachment_urls=fault.attachment_urls or [],
        is_published=fault.is_published,
        created_by=fault.created_by,
        created_at=fault.created_at,
        updated_at=fault.updated_at,
        view_count=fault.view_count,
        resolved_count=fault.resolved_count,
    )


@router.get("/faults", response_model=FaultPage, summary="后台故障列表（不含解题步骤）")
def list_faults(
    product_id: int | None = Query(None),
    part_id: int | None = Query(None),
    keyword: str | None = Query(None, max_length=100, description="匹配标题或现象"),
    is_published: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(FAULT_READ)),
) -> FaultPage:
    stmt = (
        select(Fault, Product.name, Part.name)
        .join(Product, Fault.product_id == Product.id)
        .join(Part, Fault.part_id == Part.id)
    )
    if product_id is not None:
        stmt = stmt.where(Fault.product_id == product_id)
    if part_id is not None:
        stmt = stmt.where(Fault.part_id == part_id)
    if keyword and keyword.strip():
        lowered = like_pattern(keyword.lower())
        stmt = stmt.where(
            or_(
                func.lower(Fault.title).like(lowered, escape=LIKE_ESCAPE),
                func.lower(func.coalesce(Fault.symptom, "")).like(lowered, escape=LIKE_ESCAPE),
            )
        )
    if is_published is not None:
        stmt = stmt.where(Fault.is_published.is_(is_published))

    stmt = stmt.order_by(Fault.created_at.desc(), Fault.id.desc())
    total, rows = paginate(db, stmt, page, page_size)

    return FaultPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_admin_item(fault, product_name, part_name) for fault, product_name, part_name in rows],
    )


@router.get(
    "/faults/{fault_id}",
    response_model=FaultAdminDetail,
    summary="后台故障回显（不写日志、不自增浏览数）",
    responses={404: {"model": ErrorBody, "description": "故障不存在"}},
)
def get_fault(
    fault_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(FAULT_READ)),
) -> FaultAdminDetail:
    fault = db.get(Fault, fault_id)
    if fault is None:
        raise BusinessError("NOT_FOUND", "故障不存在", 404)
    return _to_admin_detail(fault)


@router.post(
    "/faults",
    status_code=201,
    response_model=FaultAdminDetail,
    summary="新建故障",
    responses={
        400: {"model": ErrorBody, "description": "零件不属于该产品"},
        404: {"model": ErrorBody, "description": "产品或零件不存在"},
    },
)
def create_fault(
    payload: FaultCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require(FAULT_WRITE)),
) -> FaultAdminDetail:
    _ensure_product_part(db, payload.product_id, payload.part_id)

    fault = Fault(**payload.model_dump(), created_by=user.id)
    db.add(fault)
    db.commit()
    db.refresh(fault)
    return _to_admin_detail(fault)


@router.put(
    "/faults/{fault_id}",
    response_model=FaultAdminDetail,
    summary="修改故障（字段可选，解题步骤整体替换）",
    responses={
        400: {"model": ErrorBody, "description": "零件不属于该产品"},
        404: {"model": ErrorBody, "description": "故障或目标产品不存在"},
    },
)
def update_fault(
    fault_id: int,
    payload: FaultUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require(FAULT_WRITE)),
) -> FaultAdminDetail:
    fault = db.get(Fault, fault_id)
    if fault is None:
        raise BusinessError("NOT_FOUND", "故障不存在", 404)

    data = payload.model_dump(exclude_unset=True)
    for field in _NOT_NULL:
        if field in data and data[field] is None:
            data.pop(field)

    if "product_id" in data or "part_id" in data:
        _ensure_product_part(
            db, data.get("product_id", fault.product_id), data.get("part_id", fault.part_id)
        )

    for field, value in data.items():
        setattr(fault, field, value)
    fault.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(fault)
    return _to_admin_detail(fault)


@router.delete(
    "/faults/{fault_id}",
    response_model=SuccessResponse,
    summary="删除故障（工单引用置 NULL，不阻止删除）",
    responses={404: {"model": ErrorBody, "description": "故障不存在"}},
)
def delete_fault(
    fault_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(FAULT_WRITE)),
) -> SuccessResponse:
    fault = db.get(Fault, fault_id)
    if fault is None:
        raise BusinessError("NOT_FOUND", "故障不存在", 404)

    db.delete(fault)
    db.commit()
    return SuccessResponse()
