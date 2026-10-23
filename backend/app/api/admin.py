"""后台内容管理：产品与零件 CRUD（契约 §2、§3）。

简单 CRUD 直接写在这里；删除前的引用校验等稍复杂的逻辑抽成小函数，
保持每个路由函数短小、可读。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.core.exceptions import BusinessError
from app.core.permissions import (
    PART_READ,
    PART_WRITE,
    PRODUCT_READ,
    PRODUCT_WRITE,
    UPLOAD_WRITE,
    require,
)
from app.database import get_db
from app.models import Fault, Part, Product, ProductLine, User
from app.schemas.common import ErrorBody, SuccessResponse, UploadResult
from app.schemas.part import PartAdmin, PartCreate, PartPage, PartUpdate
from app.schemas.product import ProductAdmin, ProductCreate, ProductPage, ProductUpdate
from app.services.pagination import paginate
from app.services.ticket_scope import visible_line_ids
from app.services.upload_cleanup import referenced_by_fault
from app.utils.search import LIKE_ESCAPE, like_pattern
from app.utils.upload import ALLOWED_EXTENSIONS, save_upload

logger = logging.getLogger(__name__)

router = APIRouter()

# 与 save_upload 生成的存储名严格对应：{yyyyMMdd}-{8位小写hex}.{ext}
# 扩展名部分由 ALLOWED_EXTENSIONS 动态拼出，避免两处白名单不同步
_UPLOAD_NAME_RE = re.compile(
    r"^\d{8}-[0-9a-f]{8}\.(?:"
    + "|".join(sorted(ext.lstrip(".") for ext in ALLOWED_EXTENSIONS))
    + r")$"
)

# 这些字段在库中 NOT NULL，前端传 null 时直接忽略
_PRODUCT_NOT_NULL = ("name", "model", "line_id", "is_active", "sort_order")
_PART_NOT_NULL = ("name", "product_id", "sort_order")


# ---------------------------------------------------------------- 内部辅助


def _product_fault_count(db: Session, product_id: int) -> int:
    return db.scalar(select(func.count(Fault.id)).where(Fault.product_id == product_id)) or 0


def _part_fault_count(db: Session, part_id: int) -> int:
    return db.scalar(select(func.count(Fault.id)).where(Fault.part_id == part_id)) or 0


def _upload_name_from_url(url: str) -> str:
    """从上传返回的 url 中取出安全的文件名，非法输入直接 400。

    不能只用 `Path(url).name`：它能挡住 `../x`（结果是 `x`），但挡不住
    `....//` 这类畸形输入在某些平台的解析差异。这里改成**格式白名单**——
    文件名必须严格匹配 `save_upload` 生成的形态：

        {yyyyMMdd}-{8位小写16进制}.{ext}

    白名单的好处是：任何"看起来不像我们生成的"字符串一律拒绝，
    不需要考虑各种穿越变体。ext 也限定在白名单内，防止借删除接口
    去操作同目录下的其他文件（比如误留的 .part 或运维放进来的 pdf）。
    """
    name = url.rsplit("/", 1)[-1] if url else ""

    if not _UPLOAD_NAME_RE.fullmatch(name):
        raise BusinessError("VALIDATION_ERROR", "文件名不合法", 400)

    return name


def _ensure_line(db: Session, line_id: int, *, allow_inactive: bool = False) -> None:
    line = db.get(ProductLine, line_id)
    if line is None:
        raise BusinessError("NOT_FOUND", "产品线不存在", 404)
    if not line.is_active and not allow_inactive:
        raise BusinessError("LINE_INACTIVE", "产品线已停用，不能用于产品", 400)


def _to_product_admin(product: Product, fault_count: int) -> ProductAdmin:
    return ProductAdmin(
        id=product.id,
        name=product.name,
        model=product.model,
        line_id=product.line_id,
        line_name=product.line_name,
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


def _ensure_line_visible(db: Session, user: User, line_id: int, message: str) -> None:
    """LINES 数据范围的产品线写操作校验；ALL 范围不受限。"""
    line_ids = visible_line_ids(db, user)
    if line_ids is not None and line_id not in line_ids:
        raise BusinessError("PERMISSION_DENIED", message, 403)


def _ensure_model_available(db: Session, model: str, exclude_id: int | None = None) -> None:
    stmt = select(Product.id).where(Product.model == model)
    if exclude_id is not None:
        stmt = stmt.where(Product.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise BusinessError("MODEL_DUPLICATED", f"型号 {model} 已存在", 409, {"model": model})


# ---------------------------------------------------------------- 产品


@router.get("/products", response_model=ProductPage, summary="后台产品列表（含已下架）")
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=100, description="匹配名称或型号"),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require(PRODUCT_READ)),
) -> ProductPage:
    fault_count = (
        select(func.count(Fault.id))
        .where(Fault.product_id == Product.id)
        .correlate(Product)
        .scalar_subquery()
    )
    stmt = select(Product, fault_count.label("fault_count")).options(selectinload(Product.line))

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
    user: User = Depends(require(PRODUCT_WRITE)),
) -> ProductAdmin:
    _ensure_model_available(db, payload.model)
    _ensure_line(db, payload.line_id)
    _ensure_line_visible(db, user, payload.line_id, "无权在其它产品线下创建产品")

    product = Product(**payload.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:  # 并发下靠唯一约束兜底
        db.rollback()
        raise BusinessError(
            "MODEL_DUPLICATED", f"型号 {payload.model} 已存在", 409, {"model": payload.model}
        ) from exc
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
    user: User = Depends(require(PRODUCT_WRITE)),
) -> ProductAdmin:
    product = db.get(Product, product_id)
    if product is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)

    _ensure_line_visible(db, user, product.line_id, "无权修改其它产品线的产品")

    data = _drop_nulls(payload.model_dump(exclude_unset=True), _PRODUCT_NOT_NULL)
    if "model" in data and data["model"] != product.model:
        _ensure_model_available(db, data["model"], exclude_id=product_id)
    if "line_id" in data:
        _ensure_line_visible(db, user, data["line_id"], "无权把产品移到其它产品线")
        # 同一条已停用的产品线保持不变时允许，只有真正换线才校验启用状态
        if data["line_id"] != product.line_id:
            _ensure_line(db, data["line_id"])

    for field, value in data.items():
        setattr(product, field, value)
    product.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError(
            "MODEL_DUPLICATED",
            f"型号 {data.get('model', '')} 已存在",
            409,
            {"model": data.get("model", "")},
        ) from exc
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
    user: User = Depends(require(PRODUCT_WRITE)),
) -> SuccessResponse:
    product = db.get(Product, product_id)
    if product is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)

    _ensure_line_visible(db, user, product.line_id, "无权删除其它产品线的产品")

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
    _: User = Depends(require(PART_READ)),
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
    _: User = Depends(require(PART_WRITE)),
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
    _: User = Depends(require(PART_WRITE)),
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
    _: User = Depends(require(PART_WRITE)),
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
    _: User = Depends(require(UPLOAD_WRITE)),
) -> UploadResult:
    saved = await save_upload(file)
    return UploadResult(**saved)


@router.delete(
    "/upload",
    response_model=SuccessResponse,
    summary="删除未被引用的上传文件",
    responses={
        400: {"model": ErrorBody, "description": "文件名非法或路径穿越"},
        404: {"model": ErrorBody, "description": "文件不存在"},
        409: {"model": ErrorBody, "description": "文件仍被故障引用，拒绝删除"},
    },
)
def delete_upload(
    url: str = Query(..., description="上传时返回的 url，如 /uploads/20261019-a1b2c3d4.jpg"),
    db: Session = Depends(get_db),
    _: User = Depends(require(UPLOAD_WRITE)),
) -> SuccessResponse:
    """前端点"移除"时收拾掉刚上传的文件。

    修复的真实问题：改造前前端"移除"只把表单值置空，**从不通知后端**，
    文件永久留在磁盘。运营久了会把磁盘塞满（用户报障时已发现残留）。

    三条安全约束：

    1. **只接受本系统生成的文件名**。客户端传进来的字符串不能直接拼路径——
       `../../app/main.py` 这类输入必须挡在门外。用正则白名单限定格式，
       不依赖 `os.path.basename` 的"截断"行为（截断后仍可能指向目录内任意文件）。
    2. **不允许删仍被引用的文件**。同一张图可能被复制到多条方案里（用户复用），
       删了另一条方案就破图且无任何提示。这种情况返回 409，由前端静默忽略——
       文件继续留着，等孤儿清理任务在引用消失后回收。
    3. **文件不存在视为成功**。删除是幂等操作：两个标签页同时点移除，
       或清理任务刚跑过，都会出现"文件已不在"。报 404 会让用户看到无意义的错误。
    """
    name = _upload_name_from_url(url)

    db_path = Path(get_settings().upload_dir) / name
    if not db_path.is_file():
        # 幂等：已经不存在就是目标状态
        return SuccessResponse()

    if referenced_by_fault(db, {name}):
        raise BusinessError(
            "UPLOAD_IN_USE",
            "该文件仍在故障方案中使用，无法删除",
            409,
        )

    try:
        db_path.unlink()
    except PermissionError as exc:
        # 与上传同一个根因：目录属主不对。报 503 让运维按错误码查权限，
        # 不要报 500——那会让人以为是代码 bug。
        logger.error("删除上传文件失败（权限）：%s（%s）", db_path, exc)
        raise BusinessError(
            "SERVICE_UNAVAILABLE",
            "服务器暂时无法删除文件，请联系管理员",
            503,
        ) from exc
    except OSError as exc:
        logger.warning("删除上传文件失败：%s（%s）", db_path, exc)
        raise BusinessError("INTERNAL_ERROR", "删除文件失败", 500) from exc

    return SuccessResponse()
