"""进销存过账：单据创建、行锁扣减、冲正（PRD §3.5 / 定案稿 §6）。

**审批扩展口子**：L1 在 `create_document()` 内立即调用 `post_document()`，行为上仍是
「保存即生效」；未来启用「制单 → 复核」时，把这行调用挪到 confirm 端点即可，
两个函数内部一行不改，表结构与流水语义也不变。

事务边界：本模块只用 `flush()`，`commit()` 由 router 负责；任何异常冒泡后
请求级 session close 会回滚整单，不会留下半条流水。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.models import (
    InventoryBalance,
    InventoryDocument,
    InventoryDocumentItem,
    InventorySku,
    InventoryWarehouse,
    StockMovement,
    User,
)
from app.services.inventory.doc_no import next_doc_no

IN_TYPES = frozenset({"inbound", "adjust_in"})
OUT_TYPES = frozenset({"outbound", "adjust_out"})
DOC_TYPES = IN_TYPES | OUT_TYPES

# 冲正 = 生成一张方向相反的新单据，原单流水保持不动（append-only）
_REVERSE_TYPE = {
    "inbound": "outbound",
    "outbound": "inbound",
    "adjust_in": "adjust_out",
    "adjust_out": "adjust_in",
}


@dataclass(frozen=True)
class ItemInput:
    sku_id: int
    quantity: int
    unit_cost: Decimal | None = None
    remark: str | None = None


@dataclass(frozen=True)
class DocumentInput:
    doc_type: str
    warehouse_id: int
    items: tuple[ItemInput, ...]
    remark: str | None = None


def _validate(db: Session, payload: DocumentInput) -> None:
    if payload.doc_type not in DOC_TYPES:
        raise BusinessError("VALIDATION_ERROR", "单据类型不合法", 400)
    if not payload.items:
        raise BusinessError("INVENTORY_ITEM_EMPTY", "单据至少需要一条明细", 400)

    warehouse = db.get(InventoryWarehouse, payload.warehouse_id)
    if warehouse is None or not warehouse.is_active:
        raise BusinessError("NOT_FOUND", "仓库不存在或已停用", 404)

    sku_ids = {item.sku_id for item in payload.items}
    by_id = {
        row.id: row
        for row in db.scalars(select(InventorySku).where(InventorySku.id.in_(sku_ids))).all()
    }
    for item in payload.items:
        if item.quantity <= 0:
            raise BusinessError("VALIDATION_ERROR", "明细数量必须大于 0", 400)
        sku = by_id.get(item.sku_id)
        if sku is None:
            raise BusinessError("NOT_FOUND", "SKU 不存在", 404)
        if not sku.is_active:
            raise BusinessError(
                "INVENTORY_SKU_INACTIVE", f"SKU {sku.sku_no} 已停用，请移除该行", 400
            )
        if sku.warehouse_id != payload.warehouse_id:
            raise BusinessError("VALIDATION_ERROR", f"SKU {sku.sku_no} 不属于所选仓库", 400)


def create_document(db: Session, payload: DocumentInput, user: User) -> InventoryDocument:
    _validate(db, payload)
    now = datetime.now(timezone.utc)
    doc = InventoryDocument(
        doc_no=next_doc_no(db, payload.doc_type),
        doc_type=payload.doc_type,
        warehouse_id=payload.warehouse_id,
        status="confirmed",  # L1 恒 confirmed；未来启用审批时改 draft
        operator_id=user.id,
        confirmed_at=now,
        confirmed_by=user.id,
        review_remark=None,
        remark=payload.remark,
    )
    db.add(doc)
    db.flush()  # 拿 doc.id 给明细做外键
    db.add_all(
        InventoryDocumentItem(
            document_id=doc.id,
            sku_id=item.sku_id,
            quantity=item.quantity,
            unit_cost=item.unit_cost,  # 只留档：不返回、不计算（§3.6）
            remark=item.remark,
        )
        for item in payload.items
    )
    db.flush()
    post_document(db, doc, user)  # ← 未来审批时删掉这行，挪到 confirm 端点
    return doc


def _advisory_lock(db: Session, warehouse_id: int, sku_id: int) -> None:
    """余额行尚不存在时，FOR UPDATE 锁不到东西；用事务级咨询锁补上首次入库竞态。"""
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"inventory_balance:{warehouse_id}:{sku_id}"},
        )


def post_document(db: Session, doc: InventoryDocument, user: User) -> None:
    if doc.status != "confirmed":
        raise BusinessError("VALIDATION_ERROR", "单据未生效，不能过账", 400)

    # 幂等：同一单据已有流水则直接返回（防重复确认 / 重复提交造成重复扣减）
    posted = db.scalar(
        select(func.count())
        .select_from(StockMovement)
        .where(StockMovement.document_id == doc.id)
    )
    if posted:
        return

    sign = 1 if doc.doc_type in IN_TYPES else -1
    # 按 sku_id 固定顺序加锁，避免多明细单据之间互相死锁
    for item in sorted(doc.items, key=lambda it: it.sku_id):
        _advisory_lock(db, doc.warehouse_id, item.sku_id)
        _post_item(db, doc, item, sign, user)


def _post_item(
    db: Session,
    doc: InventoryDocument,
    item: InventoryDocumentItem,
    sign: int,
    user: User,
) -> None:
    stmt = select(InventoryBalance).where(
        InventoryBalance.sku_id == item.sku_id,
        InventoryBalance.warehouse_id == doc.warehouse_id,
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()  # 行锁，防并发超卖

    bal = db.execute(stmt).scalar_one_or_none()
    current = bal.quantity if bal is not None else 0
    new_qty = current + sign * item.quantity
    if new_qty < 0:
        # 抛错 → router 不 commit → 整单回滚，不留半条流水
        raise BusinessError("INSUFFICIENT_STOCK", f"库存不足，当前余额 {current}", 400)

    if bal is None:
        db.add(
            InventoryBalance(
                sku_id=item.sku_id,
                warehouse_id=doc.warehouse_id,
                quantity=new_qty,
            )
        )
    else:
        bal.quantity = new_qty

    db.add(
        StockMovement(
            sku_id=item.sku_id,
            warehouse_id=doc.warehouse_id,
            delta=sign * item.quantity,
            balance_after=new_qty,
            document_id=doc.id,
            operator_id=user.id,
        )
    )
    db.flush()


def _get_document_for_update(db: Session, document_id: int) -> InventoryDocument | None:
    """按主键取单据并加行锁，保证同一单据的改单/冲正串行。

    `populate_existing` 不能省：router 可能已在同一 session 里加载过该单据，
    不加的话 `with_for_update()` 仍返回身份映射中的旧对象（状态可能是过期的），
    锁就白加了。SQLite 单测不支持行锁，退化为普通查询。
    """
    stmt = select(InventoryDocument).where(InventoryDocument.id == document_id)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    return db.execute(stmt.execution_options(populate_existing=True)).scalar_one_or_none()


def reverse_document(
    db: Session, document_id: int, user: User, remark: str | None = None
) -> InventoryDocument:
    """冲正：生成反向单据 + 原单置 void，原单流水一条不动。"""
    doc = _get_document_for_update(db, document_id)
    if doc is None:
        raise BusinessError("NOT_FOUND", "单据不存在", 404)
    if doc.status == "void":
        raise BusinessError("DOCUMENT_ALREADY_VOIDED", "单据已冲正，不可重复操作", 400)
    if doc.status != "confirmed":
        raise BusinessError("VALIDATION_ERROR", "单据未生效，不能冲正", 400)
    reverse_type = _REVERSE_TYPE.get(doc.doc_type)
    if reverse_type is None:
        raise BusinessError("VALIDATION_ERROR", "单据类型不合法，不能冲正", 400)

    payload = DocumentInput(
        doc_type=reverse_type,
        warehouse_id=doc.warehouse_id,
        # 单价只写留档，冲正沿用原明细，避免反向单丢历史成本
        items=tuple(
            ItemInput(
                sku_id=it.sku_id,
                quantity=it.quantity,
                unit_cost=it.unit_cost,
                remark=it.remark,
            )
            for it in doc.items
        ),
        remark=f"冲正 {doc.doc_no}" + (f"：{remark}" if remark else ""),
    )
    new_doc = create_document(db, payload, user)
    doc.status = "void"
    db.flush()
    return new_doc


def _aggregate(items, sign: int) -> dict[int, int]:
    """按 SKU 汇总有符号数量（同一 SKU 可能出现在多行）。"""
    totals: dict[int, int] = {}
    for item in items:
        totals[item.sku_id] = totals.get(item.sku_id, 0) + sign * item.quantity
    return totals


def _apply_correction(
    db: Session, doc: InventoryDocument, sku_id: int, delta: int, user: User
) -> None:
    """写一条净更正流水并同步余额；delta 可为负（需扣得动）。"""
    _advisory_lock(db, doc.warehouse_id, sku_id)
    stmt = select(InventoryBalance).where(
        InventoryBalance.sku_id == sku_id,
        InventoryBalance.warehouse_id == doc.warehouse_id,
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()

    bal = db.execute(stmt).scalar_one_or_none()
    current = bal.quantity if bal is not None else 0
    new_qty = current + delta
    if new_qty < 0:
        raise BusinessError("INSUFFICIENT_STOCK", f"库存不足，当前余额 {current}", 400)

    if bal is None:
        db.add(
            InventoryBalance(
                sku_id=sku_id,
                warehouse_id=doc.warehouse_id,
                quantity=new_qty,
            )
        )
    else:
        bal.quantity = new_qty

    db.add(
        StockMovement(
            sku_id=sku_id,
            warehouse_id=doc.warehouse_id,
            delta=delta,
            balance_after=new_qty,
            document_id=doc.id,
            ref_type="document_edit",
            ref_id=str(doc.id),
            operator_id=user.id,
        )
    )
    db.flush()


def edit_document(
    db: Session, document_id: int, payload: DocumentInput, user: User
) -> InventoryDocument:
    """主管原地改写已生效入库 / 出库单：净更正流水 + 明细整体替换。

    流水 append-only，不改任何历史 `StockMovement.delta` / `balance_after`：
    逐 SKU 计算「新明细 − 旧明细」的净差额，按差额补一条更正流水，再替换明细。
    差价为 0 的 SKU 不产生流水；净差额为负且余额扣不动时整单回滚。
    """
    doc = _get_document_for_update(db, document_id)
    if doc is None:
        raise BusinessError("NOT_FOUND", "单据不存在", 404)
    if doc.status == "void":
        raise BusinessError("DOCUMENT_ALREADY_VOIDED", "单据已冲正，不可修改", 400)
    if doc.status != "confirmed":
        raise BusinessError("VALIDATION_ERROR", "单据未生效，不能修改", 400)
    if doc.doc_type not in ("inbound", "outbound"):
        raise BusinessError("VALIDATION_ERROR", "仅入库单 / 出库单可修改", 400)
    if payload.doc_type != doc.doc_type:
        raise BusinessError("VALIDATION_ERROR", "单据类型不可修改", 400)
    if payload.warehouse_id != doc.warehouse_id:
        raise BusinessError("VALIDATION_ERROR", "仓库不可修改", 400)

    _validate(db, payload)

    sign = 1 if doc.doc_type in IN_TYPES else -1
    old_totals = _aggregate(doc.items, sign)
    new_totals = _aggregate(payload.items, sign)

    for sku_id in sorted(set(old_totals) | set(new_totals)):
        delta = new_totals.get(sku_id, 0) - old_totals.get(sku_id, 0)
        if delta:
            _apply_correction(db, doc, sku_id, delta, user)

    # unit_cost 只写留档、接口不回传：改单时按 SKU 沿用旧档案，避免改数量把成本抹掉
    archived_cost: dict[int, Decimal] = {}
    for old in doc.items:
        if old.unit_cost is not None and old.sku_id not in archived_cost:
            archived_cost[old.sku_id] = old.unit_cost

    # 明细整体替换：流水挂 document_id，不挂明细 id，删旧明细不影响历史流水
    doc.items.clear()
    db.flush()
    for item in payload.items:
        doc.items.append(
            InventoryDocumentItem(
                sku_id=item.sku_id,
                quantity=item.quantity,
                # 只留档：不返回、不计算（§3.6）
                unit_cost=(
                    item.unit_cost
                    if item.unit_cost is not None
                    else archived_cost.get(item.sku_id)
                ),
                remark=item.remark,
            )
        )
    if payload.remark is not None:
        doc.remark = payload.remark
    db.flush()
    return doc


def current_balance(db: Session, sku_id: int, warehouse_id: int) -> int:
    bal = db.get(InventoryBalance, (sku_id, warehouse_id))
    return bal.quantity if bal is not None else 0


def ensure_sku_not_in_use(db: Session, sku_id: int) -> None:
    used = db.scalar(
        select(func.count())
        .select_from(InventoryDocumentItem)
        .where(InventoryDocumentItem.sku_id == sku_id)
    )
    if used:
        raise BusinessError("SKU_IN_USE", f"该 SKU 已被 {used} 条单据引用，不可停用", 409)
