"""产品线 CRUD。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.permissions import PRODUCT_LINE_READ, PRODUCT_LINE_WRITE, require
from app.database import get_db
from app.models import Product, ProductLine, User
from app.schemas.common import ErrorBody, SuccessResponse
from app.schemas.product_line import ProductLineCreate, ProductLineList, ProductLineOut, ProductLineUpdate

router = APIRouter()


def _counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Product.line_id, func.count(Product.id)).group_by(Product.line_id)
    ).all()
    return {line_id: count for line_id, count in rows}


def _to_out(line: ProductLine, counts: dict[int, int]) -> ProductLineOut:
    return ProductLineOut(
        id=line.id,
        name=line.name,
        sort_order=line.sort_order,
        is_active=line.is_active,
        product_count=counts.get(line.id, 0),
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


@router.get("/product-lines", response_model=ProductLineList, summary="产品线列表")
def list_lines(
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require(PRODUCT_LINE_READ)),
) -> ProductLineList:
    stmt = select(ProductLine).order_by(ProductLine.sort_order, ProductLine.id)
    if is_active is not None:
        stmt = stmt.where(ProductLine.is_active.is_(is_active))
    counts = _counts(db)
    return ProductLineList(items=[_to_out(line, counts) for line in db.scalars(stmt)])


@router.post(
    "/product-lines",
    status_code=201,
    response_model=ProductLineOut,
    summary="新建产品线",
    responses={409: {"model": ErrorBody, "description": "名称重复"}},
)
def create_line(
    payload: ProductLineCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require(PRODUCT_LINE_WRITE)),
) -> ProductLineOut:
    line = ProductLine(**payload.model_dump())
    db.add(line)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError("LINE_NAME_DUPLICATED", f"产品线 {payload.name} 已存在", 409) from exc
    db.refresh(line)
    return _to_out(line, {})


@router.put(
    "/product-lines/{line_id}",
    response_model=ProductLineOut,
    summary="修改产品线",
)
def update_line(
    line_id: int,
    payload: ProductLineUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require(PRODUCT_LINE_WRITE)),
) -> ProductLineOut:
    line = db.get(ProductLine, line_id)
    if line is None:
        raise BusinessError("NOT_FOUND", "产品线不存在", 404)

    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is None:
        data.pop("name", None)
    for field, value in data.items():
        setattr(line, field, value)
    line.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError(
            "LINE_NAME_DUPLICATED", f"产品线 {data.get('name', '')} 已存在", 409
        ) from exc
    db.refresh(line)
    return _to_out(line, _counts(db))


@router.delete(
    "/product-lines/{line_id}",
    response_model=SuccessResponse,
    summary="删除产品线",
    responses={409: {"model": ErrorBody, "description": "仍有产品引用"}},
)
def delete_line(
    line_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(PRODUCT_LINE_WRITE)),
) -> SuccessResponse:
    line = db.get(ProductLine, line_id)
    if line is None:
        raise BusinessError("NOT_FOUND", "产品线不存在", 404)

    product_count = db.scalar(
        select(func.count(Product.id)).where(Product.line_id == line_id)
    ) or 0
    if product_count:
        raise BusinessError(
            "DELETE_BLOCKED", f"该产品线下还有 {product_count} 个产品，请先迁移后再试", 409
        )

    db.delete(line)
    db.commit()
    return SuccessResponse()
