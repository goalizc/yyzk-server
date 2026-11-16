"""进销存：入库单 / 出库单 / 调整单 / 冲正 / 改单（PRD §4 端点 8-15、24）。

按资源拆端点，每个端点挂静态 `require(...)`；`create_document()` 在 service 层
完成建单 + 过账，router 只做参数校验、审计埋点与 `commit()`，不直接碰余额。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import BusinessError
from app.core.permissions import (
    INVENTORY_ADJUST_WRITE,
    INVENTORY_DOC_EDIT,
    INVENTORY_INBOUND_READ,
    INVENTORY_INBOUND_WRITE,
    INVENTORY_OUTBOUND_READ,
    INVENTORY_OUTBOUND_WRITE,
    require,
)
from app.core.time import to_db_datetime
from app.database import get_db
from app.models import (
    InventoryDocument,
    InventoryDocumentItem,
    InventorySku,
    InventorySkuCategory,
    InventorySkuProduct,
    User,
)
from app.schemas.common import ErrorBody
from app.schemas.inventory import (
    AdjustmentCreate,
    DocumentCreate,
    DocumentDetail,
    DocumentItem,
    DocumentItemOut,
    DocumentPage,
    DocumentUpdate,
    ReverseRequest,
)
from app.services.inventory import (
    DocumentInput,
    ItemInput,
    create_document,
    edit_document,
    reverse_document,
)
from app.utils.search import LIKE_ESCAPE, like_pattern

router = APIRouter()

_ADJUST_TYPE = {"in": "adjust_in", "out": "adjust_out"}


def _to_item(doc: InventoryDocument) -> DocumentItem:
    return DocumentItem(
        id=doc.id,
        doc_no=doc.doc_no,
        doc_type=doc.doc_type,
        status=doc.status,
        warehouse_id=doc.warehouse_id,
        operator_id=doc.operator_id,
        confirmed_at=doc.confirmed_at,
        confirmed_by=doc.confirmed_by,
        remark=doc.remark,
        created_at=doc.created_at,
    )


def _to_detail(db: Session, doc: InventoryDocument) -> DocumentDetail:
    rows = db.execute(
        select(InventoryDocumentItem, InventorySku.sku_no, InventorySku.name)
        .join(InventorySku, InventoryDocumentItem.sku_id == InventorySku.id)
        .where(InventoryDocumentItem.document_id == doc.id)
        .order_by(InventoryDocumentItem.id)
    ).all()
    return DocumentDetail(
        **_to_item(doc).model_dump(),
        items=[
            DocumentItemOut(
                sku_id=item.sku_id,
                sku_no=sku_no,
                sku_name=sku_name,
                quantity=item.quantity,
                remark=item.remark,
            )
            for item, sku_no, sku_name in rows
        ],
    )


def _doc_stmt(doc_type: str, *, doc_no: str | None, status: str | None) -> Select:
    stmt = select(InventoryDocument).where(InventoryDocument.doc_type == doc_type)
    if doc_no and doc_no.strip():
        stmt = stmt.where(
            InventoryDocument.doc_no.like(like_pattern(doc_no.strip()), escape=LIKE_ESCAPE)
        )
    if status:
        stmt = stmt.where(InventoryDocument.status == status)
    return stmt


def _apply_date(stmt: Select, db: Session, start: date | None, end: date | None) -> Select:
    tz = get_settings().timezone
    if start is not None:
        stmt = stmt.where(
            InventoryDocument.created_at
            >= to_db_datetime(db, datetime.combine(start, time.min, tzinfo=tz))
        )
    if end is not None:
        # 半开区间：< 次日 00:00，避免漏掉 23:59:59.001–.999
        stmt = stmt.where(
            InventoryDocument.created_at
            < to_db_datetime(db, datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz))
        )
    return stmt


def _list(
    db: Session,
    doc_type: str,
    *,
    doc_no: str | None,
    status: str | None,
    start_date: date | None,
    end_date: date | None,
    category_id: int | None,
    product_id: int | None,
    page: int,
    page_size: int,
) -> DocumentPage:
    stmt = _apply_date(
        _doc_stmt(doc_type, doc_no=doc_no, status=status), db, start_date, end_date
    ).order_by(InventoryDocument.created_at.desc(), InventoryDocument.id.desc())
    if category_id is not None or product_id is not None:
        # 单据含任一命中 SKU 即算命中；分类 / 产品都是多对多，各追加一次 join
        matching_docs = select(InventoryDocumentItem.document_id)
        if category_id is not None:
            matching_docs = matching_docs.join(
                InventorySkuCategory,
                InventorySkuCategory.sku_id == InventoryDocumentItem.sku_id,
            ).where(InventorySkuCategory.category_id == category_id)
        if product_id is not None:
            matching_docs = matching_docs.join(
                InventorySkuProduct,
                InventorySkuProduct.sku_id == InventoryDocumentItem.sku_id,
            ).where(InventorySkuProduct.product_id == product_id)
        stmt = stmt.where(InventoryDocument.id.in_(matching_docs))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return DocumentPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_item(doc) for doc in rows],
    )


def _get(db: Session, document_id: int, expected_type: str) -> DocumentDetail:
    doc = db.get(InventoryDocument, document_id)
    # 路径与单据类型不一致按 NOT_FOUND，避免从出库接口读到入库单（PRD §4）
    if doc is None or doc.doc_type != expected_type:
        raise BusinessError("NOT_FOUND", "单据不存在", 404)
    return _to_detail(db, doc)


def _create(
    db: Session,
    payload: DocumentCreate,
    doc_type: str,
    user: User,
    request: Request,
) -> DocumentDetail:
    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_name": "新单据",
    }
    doc = create_document(
        db,
        DocumentInput(
            doc_type=doc_type,
            warehouse_id=payload.warehouse_id,
            items=tuple(
                ItemInput(
                    sku_id=item.sku_id,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    remark=item.remark,
                )
                for item in payload.items
            ),
            remark=payload.remark,
        ),
        user,
    )
    db.commit()
    db.refresh(doc)
    request.state.audit["target_id"] = str(doc.id)
    request.state.audit["target_name"] = doc.doc_no
    return _to_detail(db, doc)


# ---------------------------------------------------------------- 入库单


@router.get("/inbound-orders", response_model=DocumentPage, summary="入库单列表")
def list_inbound(
    doc_no: str | None = Query(None, max_length=50),
    status: str | None = Query(None, max_length=20),
    category_id: int | None = Query(None, description="按 SKU 分类筛选"),
    product_id: int | None = Query(None, description="按 SKU 关联产品筛选"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_INBOUND_READ)),
) -> DocumentPage:
    return _list(
        db, "inbound", doc_no=doc_no, status=status, category_id=category_id,
        product_id=product_id,
        start_date=start_date, end_date=end_date, page=page, page_size=page_size,
    )


@router.get(
    "/inbound-orders/{document_id}",
    response_model=DocumentDetail,
    summary="入库单详情（含明细）",
    responses={404: {"model": ErrorBody, "description": "单据不存在"}},
)
def get_inbound(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_INBOUND_READ)),
) -> DocumentDetail:
    return _get(db, document_id, "inbound")


@router.post(
    "/inbound-orders",
    status_code=201,
    response_model=DocumentDetail,
    summary="登记入库",
    responses={
        400: {"model": ErrorBody, "description": "明细为空 / 停用 SKU / 参数不合法"},
        404: {"model": ErrorBody, "description": "仓库或 SKU 不存在"},
    },
)
def create_inbound(
    payload: DocumentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_INBOUND_WRITE)),
) -> DocumentDetail:
    return _create(db, payload, "inbound", user, request)


# ---------------------------------------------------------------- 出库单


@router.get("/outbound-orders", response_model=DocumentPage, summary="出库单列表")
def list_outbound(
    doc_no: str | None = Query(None, max_length=50),
    status: str | None = Query(None, max_length=20),
    category_id: int | None = Query(None, description="按 SKU 分类筛选"),
    product_id: int | None = Query(None, description="按 SKU 关联产品筛选"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_OUTBOUND_READ)),
) -> DocumentPage:
    return _list(
        db, "outbound", doc_no=doc_no, status=status, category_id=category_id,
        product_id=product_id,
        start_date=start_date, end_date=end_date, page=page, page_size=page_size,
    )


@router.get(
    "/outbound-orders/{document_id}",
    response_model=DocumentDetail,
    summary="出库单详情（含明细）",
    responses={404: {"model": ErrorBody, "description": "单据不存在"}},
)
def get_outbound(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_OUTBOUND_READ)),
) -> DocumentDetail:
    return _get(db, document_id, "outbound")


@router.post(
    "/outbound-orders",
    status_code=201,
    response_model=DocumentDetail,
    summary="登记出库（余额不足整单回滚）",
    responses={
        400: {"model": ErrorBody, "description": "库存不足 / 明细为空 / 停用 SKU"},
        404: {"model": ErrorBody, "description": "仓库或 SKU 不存在"},
    },
)
def create_outbound(
    payload: DocumentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_OUTBOUND_WRITE)),
) -> DocumentDetail:
    return _create(db, payload, "outbound", user, request)


# ---------------------------------------------------------------- 调整 / 冲正


@router.post(
    "/adjustments",
    status_code=201,
    response_model=DocumentDetail,
    summary="盘盈 / 盘亏登记",
    responses={
        400: {"model": ErrorBody, "description": "明细为空 / 库存不足 / 停用 SKU"},
        404: {"model": ErrorBody, "description": "仓库或 SKU 不存在"},
    },
)
def create_adjustment(
    payload: AdjustmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_ADJUST_WRITE)),
) -> DocumentDetail:
    return _create(db, payload, _ADJUST_TYPE[payload.adjust_type], user, request)


@router.post(
    "/documents/{document_id}/reverse",
    status_code=201,
    response_model=DocumentDetail,
    summary="冲正：生成反向单并把原单置 void",
    responses={
        400: {"model": ErrorBody, "description": "单据已冲正或状态不允许"},
        404: {"model": ErrorBody, "description": "单据不存在"},
    },
)
def reverse(
    document_id: int,
    payload: ReverseRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_ADJUST_WRITE)),
) -> DocumentDetail:
    # 审计里写单号而不是 id：审计列表按 target_name 检索，
    # 只留 id 的话事后没法按单号追溯（审查 m-08）。
    doc = db.get(InventoryDocument, document_id)
    if doc is None:
        raise BusinessError("NOT_FOUND", "单据不存在", 404)
    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_id": str(document_id),
        "target_name": f"冲正单据 {doc.doc_no}",
        "detail": {"remark": payload.remark},
    }
    new_doc = reverse_document(db, document_id, user, payload.remark)
    db.commit()
    db.refresh(new_doc)
    request.state.audit["detail"]["reverse_doc_no"] = new_doc.doc_no
    return _to_detail(db, new_doc)


# ---------------------------------------------------------------- 改单（主管）


@router.put(
    "/documents/{document_id}",
    response_model=DocumentDetail,
    summary="修改已生效入库 / 出库单（净更正流水 + 改写明细）",
    responses={
        400: {"model": ErrorBody, "description": "已冲正 / 类型不允许 / 明细为空 / 库存不足"},
        403: {"model": ErrorBody, "description": "无权限（需 inventory:doc:edit）"},
        404: {"model": ErrorBody, "description": "单据或 SKU 不存在"},
    },
)
def edit_document_endpoint(
    document_id: int,
    payload: DocumentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_DOC_EDIT)),
) -> DocumentDetail:
    doc = db.get(InventoryDocument, document_id)
    if doc is None:
        raise BusinessError("NOT_FOUND", "单据不存在", 404)
    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_id": str(doc.id),
        "target_name": doc.doc_no,
        "detail": {"item_count": len(payload.items)},
    }
    updated = edit_document(
        db,
        document_id,
        DocumentInput(
            doc_type=doc.doc_type,
            warehouse_id=doc.warehouse_id,
            items=tuple(
                ItemInput(
                    sku_id=item.sku_id,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    remark=item.remark,
                )
                for item in payload.items
            ),
            remark=payload.remark,
        ),
        user,
    )
    db.commit()
    db.refresh(updated)
    return _to_detail(db, updated)
