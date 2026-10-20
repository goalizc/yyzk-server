"""后台内容管理：产品与零件 CRUD（契约 §2、§3）。

简单 CRUD 直接写在这里；删除前的引用校验等稍复杂的逻辑抽成小函数，
保持每个路由函数短小、可读。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.exceptions import BusinessError
from app.database import get_db
from app.models import Fault, Part, Product, User
from app.schemas.common import ErrorBody, SuccessResponse, UploadResult
from app.schemas.part import PartAdmin, PartCreate, PartPage, PartUpdate
from app.schemas.product import ProductAdmin, ProductCreate, ProductPage, ProductUpdate
from app.services.pagination import paginate
from app.utils.search import LIKE_ESCAPE, like_pattern
from app.utils.upload import save_upload

router = APIRouter()

# 这些字段在库中 NOT NULL，前端传 null 时直接忽略
_PRODUCT_NOT_NULL = ("name", "model", "is_active", "sort_order")
_PART_NOT_NULL = ("name", "product_id", "sort_order")


# ---------------------------------------------------------------- 内部辅助


def _product_fault_count(db: Session, product_id: int) -> int:
    return db.scalar(select(func.count(Fault.id)).where(Fault.product_id == product_id)) or 0


def _part_fault_count(db: Session, part_id: int) -> int:
    return db.scalar(select(func.count(Fault.id)).where(Fault.part_id == part_id)) or 0


def _to_product_admin(product: Product, fault_count: int) -> ProductAdmin:
    return ProductAdmin(
        id=product.id,
        name=product.name,
        model=product.model,
        category=product.category,
        description=product.description or "",
        is_active=product.is_active,
        sort_order=product.sort_order,
        fault_count=fault_count,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _to_part_admin(part: Part, fault_count: int) -> PartAdmin:
    return PartAdmin(
        id=part.id,
        product_id=part.product_id,
        part_no=part.part_no,
        name=part.name,
        group_name=part.group_name,
        sort_order=part.sort_order,
        fault_count=fault_count,
    )


def _drop_nulls(data: dict, key: tuple[str, ...]) -> dict:
    for name in key:
        if name in data and data[name] is None:
            data.pop(name)
    return data


def _ensure_model_available(db: Session, model: str, exclude_id: int | None = None) -> None:
    stmt = select(Product.id).where(Product.model == model)
    if exclude_id is not None:
        stmt = stmt.where(Product.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise BusinessError("MODEL_DUPLICATED", f"型号 {model} 已存在", 409)


# ---------------------------------------------------------------- 产品


@router.get("/products", response_model=ProductPage, summary="后台产品列表（含已下架）")
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=100, description="匹配名称或型号"),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProductPage:
    fault_count = (
        select(func.count(Fault.id))
        .where(Fault.product_id == Product.id)
        .correlate(Product)
        .scalar_subquery()
    )
    stmt = select(Product, fault_count.label("fault_count"))

    if keyword:
        lowered = like_pattern(keyword.lower())
        stmt = stmt.where(
            or_(
                func.lower(Product.name).like(lowered, escape=LIKE_ESCAPE),
                func.lower(Product.model).like(lowered, escape=LIKE_ESCAPE),
            )
        )
    if is_active is not None:
        stmt = stmt.where(Product.is_active.is_(is_active))

    stmt = stmt.order_by(Product.sort_order, Product.id)
    total, rows = paginate(db, stmt, page, page_size)

    return ProductPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_product_admin(product, count) for product, count in rows],
    )


@router.post(
    "/products",
    status_code=201,
    response_model=ProductAdmin,
    summary="新建产品",
    responses={409: {"model": ErrorBody, "description": "型号重复"}},
)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProductAdmin:
    _ensure_model_available(db, payload.model)

    product = Product(**payload.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:  # 并发下靠唯一约束兜底
        db.rollback()
        raise BusinessError("MODEL_DUPLICATED", f"型号 {payload.model} 已存在", 409) from exc
    db.refresh(product)
    return _to_product_admin(product, 0)


@router.put(
    "/products/{product_id}",
    response_model=ProductAdmin,
    summary="修改产品（字段可选）",
    responses={
        404: {"model": ErrorBody, "description": "产品不存在"},
        409: {"model": ErrorBody, "description": "型号重复"},
    },
)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProductAdmin:
    product = db.get(Product, product_id)
    if product is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)

    data = _drop_nulls(payload.model_dump(exclude_unset=True), _PRODUCT_NOT_NULL)
    if "model" in data and data["model"] != product.model:
        _ensure_model_available(db, data["model"], exclude_id=product_id)

    for field, value in data.items():
        setattr(product, field, value)
    product.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError("MODEL_DUPLICATED", f"型号 {data.get('model', '')} 已存在", 409) from exc
    db.refresh(product)
    return _to_product_admin(product, _product_fault_count(db, product_id))


@router.delete(
    "/products/{product_id}",
    response_model=SuccessResponse,
    summary="删除产品",
    responses={
        404: {"model": ErrorBody, "description": "产品不存在"},
        409: {"model": ErrorBody, "description": "仍有零件或故障引用"},
    },
)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SuccessResponse:
    product = db.get(Product, product_id)
    if product is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)

    part_count = db.scalar(select(func.count(Part.id)).where(Part.product_id == product_id)) or 0
    fault_count = _product_fault_count(db, product_id)
    if part_count or fault_count:
        raise BusinessError(
            "DELETE_BLOCKED",
            f"该产品下还有 {part_count} 个零件、{fault_count} 条故障，请先迁移或删除后再试",
            409,
        )

    db.delete(product)
    db.commit()
    return SuccessResponse()


# ---------------------------------------------------------------- 零件


@router.get("/parts", response_model=PartPage, summary="某产品下的零件（后台，含故障数）")
def list_parts(
    product_id: int = Query(..., description="所属产品，必填"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PartPage:
    if db.get(Product, product_id) is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)

    fault_count = (
        select(func.count(Fault.id))
        .where(Fault.part_id == Part.id)
        .correlate(Part)
        .scalar_subquery()
    )
    stmt = (
        select(Part, fault_count.label("fault_count"))
        .where(Part.product_id == product_id)
        .order_by(Part.group_name, Part.sort_order, Part.id)
    )
    total, rows = paginate(db, stmt, page, page_size)

    return PartPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_part_admin(part, count) for part, count in rows],
    )


@router.post(
    "/parts",
    status_code=201,
    response_model=PartAdmin,
    summary="新建零件",
    responses={404: {"model": ErrorBody, "description": "所属产品不存在"}},
)
def create_part(
    payload: PartCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PartAdmin:
    if db.get(Product, payload.product_id) is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)

    part = Part(**payload.model_dump())
    db.add(part)
    db.commit()
    db.refresh(part)
    return _to_part_admin(part, 0)


@router.put(
    "/parts/{part_id}",
    response_model=PartAdmin,
    summary="修改零件（字段可选）",
    responses={
        404: {"model": ErrorBody, "description": "零件或目标产品不存在"},
    },
)
def update_part(
    part_id: int,
    payload: PartUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PartAdmin:
    part = db.get(Part, part_id)
    if part is None:
        raise BusinessError("NOT_FOUND", "零件不存在", 404)

    data = _drop_nulls(payload.model_dump(exclude_unset=True), _PART_NOT_NULL)
    if "product_id" in data and db.get(Product, data["product_id"]) is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)

    for field, value in data.items():
        setattr(part, field, value)
    db.commit()
    db.refresh(part)
    return _to_part_admin(part, _part_fault_count(db, part_id))


@router.delete(
    "/parts/{part_id}",
    response_model=SuccessResponse,
    summary="删除零件",
    responses={
        404: {"model": ErrorBody, "description": "零件不存在"},
        409: {"model": ErrorBody, "description": "仍有故障引用"},
    },
)
def delete_part(
    part_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SuccessResponse:
    part = db.get(Part, part_id)
    if part is None:
        raise BusinessError("NOT_FOUND", "零件不存在", 404)

    fault_count = _part_fault_count(db, part_id)
    if fault_count:
        raise BusinessError(
            "DELETE_BLOCKED", f"该零件下还有 {fault_count} 条故障，请先迁移或删除后再试", 409
        )

    db.delete(part)
    db.commit()
    return SuccessResponse()


# ---------------------------------------------------------------- 上传


@router.post(
    "/upload",
    response_model=UploadResult,
    summary="上传附件（图片/PDF/MP4，≤20MB）",
    responses={
        400: {"model": ErrorBody, "description": "类型不在白名单或文件头不匹配"},
        413: {"model": ErrorBody, "description": "文件超过大小限制"},
    },
)
async def upload_file(
    file: UploadFile = File(..., description="表单字段名 file"),
    _: User = Depends(get_current_user),
) -> UploadResult:
    saved = await save_upload(file)
    return UploadResult(**saved)
