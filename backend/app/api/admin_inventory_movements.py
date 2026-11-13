"""进销存：库存流水与 CSV 导出（PRD §4 端点 16、17）。

导出**不含 `unit_cost`**（§3.6）；CSV 公式注入防护与审计导出同源。
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.permissions import INVENTORY_EXPORT, INVENTORY_MOVEMENT_READ, require
from app.core.time import to_app_tz, to_db_datetime
from app.database import get_db
from app.models import InventoryBalance, InventoryDocument, InventorySku, StockMovement, User
from app.schemas.inventory import MovementItem, MovementPage
from app.services.pagination import paginate
from app.utils.search import LIKE_ESCAPE, like_pattern

router = APIRouter()

# 与 app/api/admin_audit.py 同源：以这些字符开头的单元格会被 Excel 当公式执行
_CSV_UNSAFE_PREFIX = ("=", "+", "-", "@", "\t", "\r")
_EXPORT_LIMIT = 5000


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in _CSV_UNSAFE_PREFIX else text


def _movement_stmt() -> Select:
    return (
        select(
            StockMovement,
            InventorySku.sku_no,
            InventorySku.name,
            InventoryDocument.doc_no,
            InventoryDocument.status,
        )
        .join(InventorySku, StockMovement.sku_id == InventorySku.id)
        .outerjoin(InventoryDocument, StockMovement.document_id == InventoryDocument.id)
    )


def _apply_filters(
    db: Session,
    stmt: Select,
    *,
    sku_id: int | None,
    doc_no: str | None,
    start_date: date | None,
    end_date: date | None,
) -> Select:
    if sku_id is not None:
        stmt = stmt.where(StockMovement.sku_id == sku_id)
    if doc_no and doc_no.strip():
        stmt = stmt.where(
            InventoryDocument.doc_no.like(like_pattern(doc_no.strip()), escape=LIKE_ESCAPE)
        )
    tz = get_settings().timezone
    if start_date is not None:
        stmt = stmt.where(
            StockMovement.created_at
            >= to_db_datetime(db, datetime.combine(start_date, time.min, tzinfo=tz))
        )
    if end_date is not None:
        stmt = stmt.where(
            StockMovement.created_at
            < to_db_datetime(db, datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz))
        )
    return stmt


def _csv_response(buffer: io.StringIO, name: str, *, total: int | None = None) -> Response:
    stamp = datetime.now(get_settings().timezone).strftime("%Y%m%d-%H%M")
    headers = {"Content-Disposition": f'attachment; filename="{name}-{stamp}.csv"'}
    # 台账导出到上限会截断：必须让前端能提示，不能让人以为数据只有这些
    if total is not None and total > _EXPORT_LIMIT:
        headers["X-Export-Truncated"] = "1"
        headers["X-Export-Total"] = str(total)
    return Response(
        # BOM：Excel 直接双击打开时中文不乱码
        content=("\ufeff" + buffer.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


@router.get("/movements", response_model=MovementPage, summary="库存流水（只读、append-only）")
def list_movements(
    sku_id: int | None = Query(None),
    doc_no: str | None = Query(None, max_length=50),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(INVENTORY_MOVEMENT_READ)),
) -> MovementPage:
    stmt = _apply_filters(
        db, _movement_stmt(),
        sku_id=sku_id, doc_no=doc_no, start_date=start_date, end_date=end_date,
    ).order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    total, rows = paginate(db, stmt, page, page_size)
    return MovementPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            MovementItem(
                id=move.id,
                sku_id=move.sku_id,
                sku_no=sku_no,
                sku_name=sku_name,
                warehouse_id=move.warehouse_id,
                delta=move.delta,
                balance_after=move.balance_after,
                document_id=move.document_id,
                doc_no=doc_no_out,
                doc_status=doc_status_out,
                operator_id=move.operator_id,
                created_at=move.created_at,
            )
            for move, sku_no, sku_name, doc_no_out, doc_status_out in rows
        ],
    )


@router.get(
    "/export",
    summary="CSV 导出（type=balance 余额 / movement 流水，不含 unit_cost）",
    response_class=Response,
)
def export_inventory(
    request: Request,
    export_type: Literal["balance", "movement"] = Query("balance", alias="type"),
    db: Session = Depends(get_db),
    user: User = Depends(require(INVENTORY_EXPORT)),
) -> Response:
    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_name": f"导出{export_type}",
    }
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    if export_type == "balance":
        qty = func.coalesce(InventoryBalance.quantity, 0)
        total = db.scalar(select(func.count()).select_from(InventorySku)) or 0
        rows = db.execute(
            select(InventorySku, qty)
            .outerjoin(
                InventoryBalance,
                (InventoryBalance.sku_id == InventorySku.id)
                & (InventoryBalance.warehouse_id == InventorySku.warehouse_id),
            )
            .order_by(InventorySku.sku_no)
            .limit(_EXPORT_LIMIT)
        ).all()
        writer.writerow(
            [_csv_cell(c) for c in
             ["SKU编码", "SKU名称", "规格", "单位", "分类", "仓库ID", "当前余额", "最低库存", "是否低库存", "状态"]]
        )
        for sku, quantity in rows:
            category_names = "/".join(c.name for c in sku.categories)
            writer.writerow(
                [_csv_cell(c) for c in [
                    sku.sku_no, sku.name, sku.spec or "", sku.unit, category_names,
                    sku.warehouse_id, int(quantity or 0), sku.min_stock,
                    "是" if int(quantity or 0) < sku.min_stock else "否",
                    "启用" if sku.is_active else "停用",
                ]]
            )
        return _csv_response(buffer, "inventory-balance", total=total)

    total = db.scalar(select(func.count()).select_from(StockMovement)) or 0
    rows = db.execute(
        _movement_stmt().order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(_EXPORT_LIMIT)
    ).all()
    writer.writerow(
        [_csv_cell(c) for c in
         ["时间", "SKU编码", "SKU名称", "仓库ID", "变动量", "变动后余额", "单据号", "操作人ID"]]
    )
    for move, sku_no, sku_name, doc_no, _ in rows:
        writer.writerow(
            [_csv_cell(c) for c in [
                to_app_tz(move.created_at).isoformat(), sku_no, sku_name,
                move.warehouse_id, move.delta, move.balance_after,
                doc_no or "", move.operator_id or "",
            ]]
        )
    return _csv_response(buffer, "inventory-movements", total=total)
