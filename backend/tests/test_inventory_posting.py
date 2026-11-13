"""进销存过账 service 专项验收（PRD 任务卡 #3 / §12）。

SQLite 单测覆盖余额、流水、整单回滚、幂等、冲正与弱关联；
PG 专属的行锁与 append-only 触发器留任务卡 #9 真机验证。
"""

from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import func, select

from app.core.exceptions import BusinessError
from app.models import (
    InventorySku,
    InventoryWarehouse,
    StockMovement,
)
from app.services.inventory import (
    DocumentInput,
    ItemInput,
    create_document,
    current_balance,
    post_document,
    reverse_document,
)
from tests.conftest import make_user


def _warehouse(db: object) -> InventoryWarehouse:
    row = InventoryWarehouse(code="DEFAULT", name="默认仓")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _sku(db: object, warehouse: InventoryWarehouse, sku_no: str = "WL-0001", **kwargs) -> InventorySku:
    row = InventorySku(
        sku_no=sku_no,
        name=f"物资-{sku_no}",
        warehouse_id=warehouse.id,
        **kwargs,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# 用户名必须真正唯一：id(items) 会被 CPython 复用，同一测试内两次调用可能撞车
_user_seq = count(1)


def _inbound(db, warehouse_id, *items, remark=None):
    user = make_user(db, username=f"op_{next(_user_seq)}")
    doc = create_document(
        db,
        DocumentInput(
            doc_type="inbound",
            warehouse_id=warehouse_id,
            items=tuple(items),
            remark=remark,
        ),
        user,
    )
    db.commit()
    return doc, user


def test_inbound_posts_balance_and_movement(db):
    warehouse = _warehouse(db)
    sku = _sku(db, warehouse)
    doc, user = _inbound(
        db,
        warehouse.id,
        ItemInput(sku_id=sku.id, quantity=20, unit_cost=Decimal("35.50")),
    )

    # 防回归（定案稿 §6.6）：L1 单据天然已生效，confirmed_by 必须非空
    assert doc.status == "confirmed"
    assert doc.confirmed_by == user.id
    assert doc.confirmed_at is not None
    assert doc.operator_id == user.id
    assert doc.doc_no.startswith("RK") and len(doc.doc_no) == 14

    assert current_balance(db, sku.id, warehouse.id) == 20
    moves = db.scalars(
        select(StockMovement).where(StockMovement.document_id == doc.id)
    ).all()
    assert len(moves) == 1
    assert moves[0].delta == 20
    assert moves[0].balance_after == 20


def test_doc_no_increments_within_same_day(db):
    warehouse = _warehouse(db)
    sku = _sku(db, warehouse)
    first, _ = _inbound(db, warehouse.id, ItemInput(sku_id=sku.id, quantity=1))
    second, _ = _inbound(db, warehouse.id, ItemInput(sku_id=sku.id, quantity=1))
    assert first.doc_no[:-4] == second.doc_no[:-4]
    assert int(second.doc_no[-4:]) == int(first.doc_no[-4:]) + 1


def test_outbound_decreases_balance(db):
    warehouse = _warehouse(db)
    sku = _sku(db, warehouse)
    _inbound(db, warehouse.id, ItemInput(sku_id=sku.id, quantity=10))
    user = make_user(db, username="outbound_op")

    doc = create_document(
        db,
        DocumentInput(
            doc_type="outbound",
            warehouse_id=warehouse.id,
            items=(ItemInput(sku_id=sku.id, quantity=4),),
        ),
        user,
    )
    db.commit()

    assert doc.doc_no.startswith("CK")
    assert current_balance(db, sku.id, warehouse.id) == 6
    move = db.scalar(select(StockMovement).where(StockMovement.document_id == doc.id))
    assert move.delta == -4 and move.balance_after == 6


def test_insufficient_stock_rolls_back_whole_document(db):
    warehouse = _warehouse(db)
    sku = _sku(db, warehouse)
    _inbound(db, warehouse.id, ItemInput(sku_id=sku.id, quantity=10))
    user = make_user(db, username="shortage_op")

    with pytest.raises(BusinessError) as exc:
        create_document(
            db,
            DocumentInput(
                doc_type="outbound",
                warehouse_id=warehouse.id,
                items=(ItemInput(sku_id=sku.id, quantity=15),),
            ),
            user,
        )
        db.commit()
    db.rollback()
    assert exc.value.code == "INSUFFICIENT_STOCK"

    # 余额与流水都不变：不能留半条流水
    assert current_balance(db, sku.id, warehouse.id) == 10
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 1


def test_post_document_is_idempotent(db):
    warehouse = _warehouse(db)
    sku = _sku(db, warehouse)
    doc, user = _inbound(db, warehouse.id, ItemInput(sku_id=sku.id, quantity=7))

    post_document(db, doc, user)
    post_document(db, doc, user)
    db.commit()

    assert current_balance(db, sku.id, warehouse.id) == 7
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 1


def test_reverse_creates_opposite_document_and_voids_original(db):
    warehouse = _warehouse(db)
    sku = _sku(db, warehouse)
    doc, user = _inbound(db, warehouse.id, ItemInput(sku_id=sku.id, quantity=10))

    reverse = reverse_document(db, doc.id, user, remark="登记错误")
    db.commit()

    assert reverse.doc_type == "outbound"
    assert reverse.remark.startswith("冲正 ")
    assert "登记错误" in reverse.remark
    assert doc.status == "void"
    assert current_balance(db, sku.id, warehouse.id) == 0
    # 原单流水一条不动，只新增反向单的流水
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 2

    with pytest.raises(BusinessError) as exc:
        reverse_document(db, doc.id, user)
    assert exc.value.code == "DOCUMENT_ALREADY_VOIDED"


def test_pure_material_without_part_can_be_stocked(db):
    """弱关联：不属于任何产品的纯物资同样能建 SKU 与出入库。"""
    warehouse = _warehouse(db)
    sku = _sku(db, warehouse, sku_no="WL-PURE", part_id=None, min_stock=2)
    assert sku.part_id is None

    _inbound(db, warehouse.id, ItemInput(sku_id=sku.id, quantity=5))
    assert current_balance(db, sku.id, warehouse.id) == 5


def test_empty_items_and_inactive_sku_rejected(db):
    warehouse = _warehouse(db)
    sku = _sku(db, warehouse)
    user = make_user(db, username="validator_op")

    with pytest.raises(BusinessError) as empty:
        create_document(
            db,
            DocumentInput(doc_type="inbound", warehouse_id=warehouse.id, items=()),
            user,
        )
    assert empty.value.code == "INVENTORY_ITEM_EMPTY"

    sku.is_active = False
    db.commit()
    with pytest.raises(BusinessError) as inactive:
        create_document(
            db,
            DocumentInput(
                doc_type="inbound",
                warehouse_id=warehouse.id,
                items=(ItemInput(sku_id=sku.id, quantity=1),),
            ),
            user,
        )
    assert inactive.value.code == "INVENTORY_SKU_INACTIVE"


def test_unit_cost_is_write_only(db):
    """§3.6：单价只留档，不影响任何余额或流水计算。"""
    warehouse = _warehouse(db)
    sku = _sku(db, warehouse)
    doc, _ = _inbound(
        db,
        warehouse.id,
        ItemInput(sku_id=sku.id, quantity=3, unit_cost=Decimal("9999.99")),
    )
    assert doc.items[0].unit_cost == Decimal("9999.99")
    assert current_balance(db, sku.id, warehouse.id) == 3
