"""进销存：仓库 / 引用数据 / SKU / 分类 / 低库存 / 后台汇总（PRD §4 端点 1-7、18-23）。

库存域数据范围统一 ALL，不复用 `apply_ticket_scope`：纯物资 `part_id` 为空，
按产品线过滤会让谁都看不见它（PRD §6.1）。
"""

from __future__ import annotations

from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import BusinessError
from app.core.permissions import INVENTORY_SKU_READ, INVENTORY_SKU_WRITE, require
from app.core.time import to_db_datetime
from app.database import get_db
from app.models import (
    InventoryBalance,
    InventoryCategory,
    InventoryDocument,
    InventorySku,
    InventorySkuCategory,
    InventorySkuProduct,
    InventoryWarehouse,
    Part,
    Product,
    StockMovement,
    User,
)
from app.schemas.common import ErrorBody, SuccessResponse
from app.schemas.inventory import (
    CategoryCreate,
    CategoryItem,
    CategoryPage,
    CategoryRef,
    CategoryUpdate,
    InventorySummary,
    LowStockItem,
    LowStockPage,
    ProductRef,
    RecentMovement,
    RefPart,
    RefProduct,
    SkuCreate,
    SkuDetail,
    SkuItem,
    SkuPage,
    SkuUpdate,
    WarehouseItem,
    WarehousePage,
)
from app.services.inventory import current_balance, ensure_sku_not_in_use
from app.services.pagination import paginate
from app.utils.search import LIKE_ESCAPE, like_pattern

router = APIRouter()

# 库中 NOT NULL；编辑时前端传 null 一律忽略，不把字段写成空
_SKU_NOT_NULL = ("name", "unit", "min_stock", "is_active")


def _balance_join(stmt: Select) -> Select:
    """余额按 (sku_id, warehouse_id) 复合主键挂；还没入过库的 SKU 视作 0。"""
    return stmt.outerjoin(
        InventoryBalance,
        (InventoryBalance.sku_id == InventorySku.id)
        & (InventoryBalance.warehouse_id == InventorySku.warehouse_id),
    )


def _sku_stmt() -> Select:
    return _balance_join(
        select(InventorySku, Part.name.label("part_name")).outerjoin(
            Part, InventorySku.part_id == Part.id
        )
    )


def _to_sku_item(sku: InventorySku, part_name: str | None, quantity: int) -> SkuItem:
    return SkuItem(
        id=sku.id,
        sku_no=sku.sku_no,
        name=sku.name,
        spec=sku.spec,
        unit=sku.unit,
        part_id=sku.part_id,
        part_name=part_name,
        warehouse_id=sku.warehouse_id,
        min_stock=sku.min_stock,
        quantity=int(quantity or 0),
        batch_no=sku.batch_no,
        is_active=sku.is_active,
        remark=sku.remark,
        categories=[CategoryRef(id=c.id, name=c.name) for c in sku.categories],
        products=[ProductRef(id=p.id, name=p.name) for p in sku.products],
        created_at=sku.created_at,
        updated_at=sku.updated_at,
    )


def _ensure_warehouse(db: Session, warehouse_id: int) -> None:
    row = db.get(InventoryWarehouse, warehouse_id)
    if row is None or not row.is_active:
        raise BusinessError("NOT_FOUND", "仓库不存在或已停用", 404)


def _ensure_part(db: Session, part_id: int | None) -> None:
    if part_id is not None and db.get(Part, part_id) is None:
        raise BusinessError("NOT_FOUND", "关联零件不存在", 404)


def _ensure_sku_no_available(db: Session, sku_no: str) -> None:
    if db.scalar(select(InventorySku.id).where(InventorySku.sku_no == sku_no)) is not None:
        raise BusinessError("SKU_NO_DUPLICATED", f"SKU 编码 {sku_no} 已存在", 409)


def _resolve_categories(db: Session, ids: list[int]) -> list[InventoryCategory]:
    result: list[InventoryCategory] = []
    for cid in ids:
        row = db.get(InventoryCategory, cid)
        if row is None:
            raise BusinessError("NOT_FOUND", f"分类不存在: {cid}", 404)
        result.append(row)
    return result


def _resolve_products(db: Session, ids: list[int]) -> list["Product"]:
    result: list[Product] = []
    for pid in ids:
        row = db.get(Product, pid)
        if row is None:
            raise BusinessError("NOT_FOUND", f"产品不存在: {pid}", 404)
        result.append(row)
    return result


# ---------------------------------------------------------------- 仓库


@router.get("/warehouses", response_model=WarehousePage, summary="仓库下拉（一期 1 条）")
def list_warehouses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_SKU_READ)),
) -> WarehousePage:
    stmt = select(InventoryWarehouse).where(InventoryWarehouse.is_active.is_(True))
    stmt = stmt.order_by(InventoryWarehouse.id)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return WarehousePage(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            WarehouseItem(id=row.id, code=row.code, name=row.name, is_active=row.is_active)
            for row in rows
        ],
    )


# ---------------------------------------------------------------- 引用数据
#
# 仓管没有 `product:read` / `part:read`（售后域权限），但建 SKU 要选关联产品/零件、
# 单据列表要按产品筛选，否则那两个下拉对仓管恒为空（403 被前端 catch 成 []）。
# 这里只暴露 id / 名称 / 型号这类引用字段，挂 `inventory:sku:read`，
# 让仓管在自己的权限域内完成选型——不要图省事直接授予售后读权限：
# 那会让其落地页变成产品目录、侧边栏冒出售后菜单。


@router.get(
    "/refs/products",
    response_model=list[RefProduct],
    summary="库存域引用：产品下拉（只读，含已停用）",
)
def list_ref_products(
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_SKU_READ)),
) -> list[RefProduct]:
    rows = db.execute(
        select(Product.id, Product.name, Product.model).order_by(
            Product.sort_order, Product.id
        )
    ).all()
    return [RefProduct(id=r[0], name=r[1], model=r[2]) for r in rows]


@router.get(
    "/refs/parts",
    response_model=list[RefPart],
    summary="库存域引用：零件下拉（只读；省略 product_id 返回全部）",
    responses={404: {"model": ErrorBody, "description": "产品不存在"}},
)
def list_ref_parts(
    product_id: int | None = Query(None, description="所属产品；省略则返回全部零件"),
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_SKU_READ)),
) -> list[RefPart]:
    if product_id is not None and db.get(Product, product_id) is None:
        raise BusinessError("NOT_FOUND", "产品不存在", 404)
    stmt = (
        select(Part.id, Part.name, Part.part_no, Part.product_id, Product.name)
        .join(Product, Part.product_id == Product.id)
        .order_by(Product.sort_order, Product.id, Part.sort_order, Part.id)
    )
    if product_id is not None:
        stmt = stmt.where(Part.product_id == product_id)
    rows = db.execute(stmt).all()
    return [
        RefPart(
            id=row[0],
            name=row[1],
            part_no=row[2],
            product_id=row[3],
            product_name=row[4],
        )
        for row in rows
    ]


# ---------------------------------------------------------------- SKU


@router.get("/skus", response_model=SkuPage, summary="SKU 列表（含当前余额）")
def list_skus(
    keyword: str | None = Query(None, max_length=100),
    category_id: int | None = Query(None, description="按分类筛选（多对多，命中任一即列出）"),
    product_id: int | None = Query(None, description="按产品筛选（多对多，命中即列出）"),
    is_active: bool | None = Query(None),
    low_stock: bool | None = Query(None, description="只看低于最低库存的 SKU"),
    part_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_SKU_READ)),
) -> SkuPage:
    qty = func.coalesce(InventoryBalance.quantity, 0)
    stmt = _sku_stmt().add_columns(qty.label("quantity"))
    if keyword and keyword.strip():
        pattern = like_pattern(keyword.strip().lower())
        stmt = stmt.where(
            or_(
                func.lower(InventorySku.sku_no).like(pattern, escape=LIKE_ESCAPE),
                func.lower(InventorySku.name).like(pattern, escape=LIKE_ESCAPE),
            )
        )
    if category_id is not None:
        stmt = stmt.where(
            InventorySku.id.in_(
                select(InventorySkuCategory.sku_id).where(
                    InventorySkuCategory.category_id == category_id
                )
            )
        )
    if product_id is not None:
        stmt = stmt.where(
            InventorySku.id.in_(
                select(InventorySkuProduct.sku_id).where(
                    InventorySkuProduct.product_id == product_id
                )
            )
        )
    if is_active is not None:
        stmt = stmt.where(InventorySku.is_active.is_(is_active))
    if low_stock:
        stmt = stmt.where(qty < InventorySku.min_stock)
    if part_id is not None:
        stmt = stmt.where(InventorySku.part_id == part_id)

    stmt = stmt.order_by(InventorySku.created_at.desc(), InventorySku.id.desc())
    total, rows = paginate(db, stmt, page, page_size)
    return SkuPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_sku_item(sku, part_name, quantity) for sku, part_name, quantity in rows],
    )


@router.get(
    "/skus/{sku_id}",
    response_model=SkuDetail,
    summary="SKU 详情（当前余额 + 最近 10 条流水）",
    responses={404: {"model": ErrorBody, "description": "SKU 不存在"}},
)
def get_sku(
    sku_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_SKU_READ)),
) -> SkuDetail:
    sku = db.get(InventorySku, sku_id)
    if sku is None:
        raise BusinessError("NOT_FOUND", "SKU 不存在", 404)
    part_name = db.get(Part, sku.part_id).name if sku.part_id else None
    item = _to_sku_item(sku, part_name, current_balance(db, sku.id, sku.warehouse_id))

    rows = db.execute(
        select(StockMovement, InventoryDocument.doc_no)
        .outerjoin(InventoryDocument, StockMovement.document_id == InventoryDocument.id)
        .where(StockMovement.sku_id == sku.id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(10)
    ).all()
    return SkuDetail(
        **item.model_dump(),
        recent_movements=[
            RecentMovement(
                id=move.id,
                delta=move.delta,
                balance_after=move.balance_after,
                doc_no=doc_no,
                created_at=move.created_at,
            )
            for move, doc_no in rows
        ],
    )


@router.post(
    "/skus",
    status_code=201,
    response_model=SkuItem,
    summary="新建 SKU",
    responses={
        404: {"model": ErrorBody, "description": "仓库或零件不存在"},
        409: {"model": ErrorBody, "description": "SKU 编码重复"},
    },
)
def create_sku(
    payload: SkuCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_SKU_WRITE)),
) -> SkuItem:
    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_name": f"{payload.sku_no} {payload.name}",
    }
    _ensure_warehouse(db, payload.warehouse_id)
    _ensure_part(db, payload.part_id)
    _ensure_sku_no_available(db, payload.sku_no)

    # 多对多关联单独解析（并非模型列，不能进 InventorySku(**dump)）
    categories = _resolve_categories(db, payload.category_ids)
    products = _resolve_products(db, payload.product_ids)
    column_data = payload.model_dump(exclude={"category_ids", "product_ids"})
    sku = InventorySku(**column_data)
    sku.categories = categories
    sku.products = products
    db.add(sku)
    try:
        db.commit()
    except IntegrityError as exc:  # 并发下靠唯一约束兜底
        db.rollback()
        raise BusinessError("SKU_NO_DUPLICATED", f"SKU 编码 {payload.sku_no} 已存在", 409) from exc
    db.refresh(sku)
    request.state.audit["target_id"] = str(sku.id)
    part_name = db.get(Part, sku.part_id).name if sku.part_id else None
    return _to_sku_item(sku, part_name, 0)


@router.put(
    "/skus/{sku_id}",
    response_model=SkuItem,
    summary="编辑 SKU（sku_no / warehouse_id 不可改）",
    responses={404: {"model": ErrorBody, "description": "SKU 或零件不存在"}},
)
def update_sku(
    sku_id: int,
    payload: SkuUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_SKU_WRITE)),
) -> SkuItem:
    sku = db.get(InventorySku, sku_id)
    if sku is None:
        raise BusinessError("NOT_FOUND", "SKU 不存在", 404)
    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_id": str(sku.id),
        "target_name": sku.name,
    }

    data = payload.model_dump(exclude_unset=True)
    for field in _SKU_NOT_NULL:
        if field in data and data[field] is None:
            data.pop(field)

    # 停用是软删：必须与 DELETE 端点同一条规则，否则被单据引用的 SKU
    # 可以从编辑表单绕过 SKU_IN_USE，之后历史单据无法冲正/改单。
    if data.get("is_active") is False and sku.is_active:
        ensure_sku_not_in_use(db, sku.id)

    # 多对多关联：传了就整体替换，没传（None）则保持原状
    cat_ids = data.pop("category_ids", None)
    prod_ids = data.pop("product_ids", None)
    if "part_id" in data:
        _ensure_part(db, data["part_id"])

    for field, value in data.items():
        setattr(sku, field, value)

    if cat_ids is not None:
        sku.categories = _resolve_categories(db, cat_ids)
    if prod_ids is not None:
        sku.products = _resolve_products(db, prod_ids)

    sku.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sku)
    part_name = db.get(Part, sku.part_id).name if sku.part_id else None
    return _to_sku_item(sku, part_name, current_balance(db, sku.id, sku.warehouse_id))


@router.delete(
    "/skus/{sku_id}",
    response_model=SuccessResponse,
    summary="停用 SKU（软删；被单据引用则拒绝）",
    responses={
        404: {"model": ErrorBody, "description": "SKU 不存在"},
        409: {"model": ErrorBody, "description": "SKU 已被单据引用"},
    },
)
def disable_sku(
    sku_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_SKU_WRITE)),
) -> SuccessResponse:
    sku = db.get(InventorySku, sku_id)
    if sku is None:
        raise BusinessError("NOT_FOUND", "SKU 不存在", 404)
    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_id": str(sku.id),
        "target_name": sku.name,
    }
    ensure_sku_not_in_use(db, sku.id)
    sku.is_active = False
    sku.updated_at = datetime.now(timezone.utc)
    db.commit()
    return SuccessResponse()


# ---------------------------------------------------------------- 分类主数据（数据表管理）


@router.get("/categories", response_model=CategoryPage, summary="物资分类列表")
def list_categories(
    keyword: str | None = Query(None, max_length=50),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_SKU_READ)),
) -> CategoryPage:
    stmt = select(InventoryCategory)
    if keyword and keyword.strip():
        pattern = like_pattern(keyword.strip().lower())
        stmt = stmt.where(func.lower(InventoryCategory.name).like(pattern, escape=LIKE_ESCAPE))
    if is_active is not None:
        stmt = stmt.where(InventoryCategory.is_active.is_(is_active))
    stmt = stmt.order_by(InventoryCategory.name)
    total, rows = paginate(db, stmt, page, page_size)
    return CategoryPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            CategoryItem(
                id=row[0].id,
                name=row[0].name,
                is_active=row[0].is_active,
                remark=row[0].remark,
                created_at=row[0].created_at,
                updated_at=row[0].updated_at,
            )
            for row in rows
        ],
    )


@router.post(
    "/categories",
    status_code=201,
    response_model=CategoryItem,
    summary="新建物资分类",
    responses={409: {"model": ErrorBody, "description": "分类名称重复"}},
)
def create_category(
    payload: CategoryCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_SKU_WRITE)),
) -> CategoryItem:
    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_name": payload.name,
    }
    row = InventoryCategory(name=payload.name, remark=payload.remark)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BusinessError("CATEGORY_NAME_DUPLICATED", f"分类名称 {payload.name} 已存在", 409)
    db.refresh(row)
    request.state.audit["target_id"] = str(row.id)
    return CategoryItem(
        id=row.id,
        name=row.name,
        is_active=row.is_active,
        remark=row.remark,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.put(
    "/categories/{category_id}",
    response_model=CategoryItem,
    summary="编辑物资分类（名称 / 备注 / 启停）",
    responses={
        404: {"model": ErrorBody, "description": "分类不存在"},
        409: {"model": ErrorBody, "description": "分类名称重复"},
    },
)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_SKU_WRITE)),
) -> CategoryItem:
    row = db.get(InventoryCategory, category_id)
    if row is None:
        raise BusinessError("NOT_FOUND", "分类不存在", 404)
    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_id": str(row.id),
        "target_name": row.name,
    }
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BusinessError("CATEGORY_NAME_DUPLICATED", f"分类名称 {row.name} 已存在", 409)
    db.refresh(row)
    return CategoryItem(
        id=row.id,
        name=row.name,
        is_active=row.is_active,
        remark=row.remark,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------- 低库存 / 汇总


@router.get("/low-stock", response_model=LowStockPage, summary="低库存清单")
def list_low_stock(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_SKU_READ)),
) -> LowStockPage:
    qty = func.coalesce(InventoryBalance.quantity, 0)
    stmt = _balance_join(select(InventorySku, qty.label("quantity"))).where(
        InventorySku.is_active.is_(True), qty < InventorySku.min_stock
    )
    stmt = stmt.order_by((InventorySku.min_stock - qty).desc(), InventorySku.id)
    total, rows = paginate(db, stmt, page, page_size)
    return LowStockPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            LowStockItem(
                id=sku.id,
                sku_no=sku.sku_no,
                name=sku.name,
                unit=sku.unit,
                warehouse_id=sku.warehouse_id,
                min_stock=sku.min_stock,
                quantity=int(quantity or 0),
                shortage=sku.min_stock - int(quantity or 0),
            )
            for sku, quantity in rows
        ],
    )


@router.get("/summary", response_model=InventorySummary, summary="后台首页库存卡片")
def inventory_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_SKU_READ)),
) -> InventorySummary:
    qty = func.coalesce(InventoryBalance.quantity, 0)
    low_stmt = _balance_join(select(func.count()).select_from(InventorySku)).where(
        InventorySku.is_active.is_(True), qty < InventorySku.min_stock
    )

    tz = get_settings().timezone
    month_start = datetime.combine(
        datetime.now(tz).date().replace(day=1), time.min, tzinfo=tz
    )
    since = to_db_datetime(db, month_start)

    def _docs(doc_type: str) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(InventoryDocument)
                .where(
                    InventoryDocument.doc_type == doc_type,
                    InventoryDocument.created_at >= since,
                )
            )
            or 0
        )

    return InventorySummary(
        sku_count=db.scalar(
            select(func.count()).select_from(InventorySku).where(InventorySku.is_active.is_(True))
        )
        or 0,
        low_stock_count=db.scalar(low_stmt) or 0,
        inbound_this_month=_docs("inbound"),
        outbound_this_month=_docs("outbound"),
    )
