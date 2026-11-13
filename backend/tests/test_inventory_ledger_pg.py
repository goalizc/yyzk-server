"""PG 全链路账务闭环回归：入库/出库/盘点/改单/冲正 + 对账。

默认跳过；需要显式提供一次性 PostgreSQL 库：

    PG_TEST_DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db \
      .venv/bin/python -m pytest backend/tests/test_inventory_ledger_pg.py -q

测试在目标库内建独立 schema，结束时 DROP SCHEMA ... CASCADE，不会碰已有表。
SQLite 单测覆盖不到行锁与 append-only 触发器，故这条只跑 PostgreSQL。
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.database import Base
from app.models import (
    InventoryDocument,
    InventoryDocumentItem,
    InventorySku,
    InventoryWarehouse,
    StockMovement,
    User,
)
from app.services.inventory import (
    DocumentInput,
    ItemInput,
    create_document,
    current_balance,
    edit_document,
    reverse_document,
)

PG_URL = os.getenv("PG_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL, reason="需要 PG_TEST_DATABASE_URL 指向一次性 PostgreSQL 库"
)

_TRIGGERS = """
CREATE OR REPLACE FUNCTION stock_movements_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'append-only（测试）',
        HINT = '如需更正请登记冲正单';
END $$;

CREATE TRIGGER trg_stock_movements_immutable
    BEFORE UPDATE OR DELETE ON stock_movements
    FOR EACH ROW EXECUTE FUNCTION stock_movements_immutable();

CREATE TRIGGER trg_stock_movements_no_truncate
    BEFORE TRUNCATE ON stock_movements
    FOR EACH STATEMENT EXECUTE FUNCTION stock_movements_immutable();
"""


@pytest.fixture()
def engine():
    schema = f"inv_ledger_{uuid.uuid4().hex[:8]}"
    engine = create_engine(PG_URL, connect_args={"options": f"-csearch_path={schema}"})
    with engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
        Base.metadata.create_all(conn)
        conn.exec_driver_sql(_TRIGGERS)
    try:
        yield engine
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
        engine.dispose()


def _seed(engine) -> tuple[int, int, int]:
    with Session(engine) as db:
        user = User(
            username="ledger_op",
            password_hash="x",
            real_name="对账",
            role="super_admin",
        )
        warehouse = InventoryWarehouse(code="DEFAULT", name="默认仓")
        db.add_all([user, warehouse])
        db.commit()
        sku = InventorySku(sku_no="WL-LEDGER", name="对账物资", warehouse_id=warehouse.id)
        db.add(sku)
        db.commit()
        return user.id, warehouse.id, sku.id


def _create(db: Session, warehouse_id: int, doc_type: str, items: list[ItemInput], user: User):
    doc = create_document(
        db,
        DocumentInput(doc_type=doc_type, warehouse_id=warehouse_id, items=tuple(items)),
        user,
    )
    db.commit()
    return doc


def test_full_ledger_flow_closes(engine) -> None:
    user_id, warehouse_id, sku_id = _seed(engine)

    with Session(engine) as db:
        user = db.get(User, user_id)

        # 100 入 → 30 出 → 盘盈 5 → 盘亏 2；余额 73
        inbound = _create(
            db, warehouse_id, "inbound",
            [ItemInput(sku_id, 100, unit_cost=Decimal("12.50"))], user,
        )
        outbound = _create(
            db, warehouse_id, "outbound",
            [ItemInput(sku_id, 30, unit_cost=Decimal("9.99"))], user,
        )
        _create(db, warehouse_id, "adjust_in", [ItemInput(sku_id, 5)], user)
        _create(db, warehouse_id, "adjust_out", [ItemInput(sku_id, 2)], user)
        assert current_balance(db, sku_id, warehouse_id) == 73

        # 改单 30 → 40：净更正 -10，余额 63；原流水一条不动
        edit_document(
            db,
            outbound.id,
            DocumentInput(
                doc_type="outbound",
                warehouse_id=warehouse_id,
                items=(ItemInput(sku_id, 40),),
            ),
            user,
        )
        db.commit()
        assert current_balance(db, sku_id, warehouse_id) == 63
        corrections = db.scalars(
            select(StockMovement).where(
                StockMovement.document_id == outbound.id,
                StockMovement.ref_type == "document_edit",
            )
        ).all()
        assert [(m.delta, m.balance_after) for m in corrections] == [(-10, 63)]

        # 冲正出库单（当前 40）：余额 103，原单 void
        reverse_out = reverse_document(db, outbound.id, user, "改单后冲正")
        db.commit()
        assert current_balance(db, sku_id, warehouse_id) == 103
        assert reverse_out.doc_type == "inbound"

        # 冲正入库单（100）：余额 3，原单 void
        reverse_in = reverse_document(db, inbound.id, user, "入库错误")
        db.commit()
        assert current_balance(db, sku_id, warehouse_id) == 3
        assert reverse_in.doc_type == "outbound"

        # 超卖整单回滚：余额与流水条数都不变
        before_moves = db.scalar(select(func.count()).select_from(StockMovement))
        with pytest.raises(BusinessError) as oversell:
            create_document(
                db,
                DocumentInput(
                    doc_type="outbound",
                    warehouse_id=warehouse_id,
                    items=(ItemInput(sku_id, 1000),),
                ),
                user,
            )
        db.rollback()
        assert oversell.value.code == "INSUFFICIENT_STOCK"
        assert db.scalar(select(func.count()).select_from(StockMovement)) == before_moves

        # 已冲正单据不能再冲正 / 改单
        with pytest.raises(BusinessError) as again:
            reverse_document(db, outbound.id, user)
        assert again.value.code == "DOCUMENT_ALREADY_VOIDED"
        db.rollback()
        with pytest.raises(BusinessError) as edit_void:
            edit_document(
                db,
                outbound.id,
                DocumentInput(
                    doc_type="outbound",
                    warehouse_id=warehouse_id,
                    items=(ItemInput(sku_id, 41),),
                ),
                user,
            )
        assert edit_void.value.code == "DOCUMENT_ALREADY_VOIDED"
        db.rollback()

        # 状态、单号前缀与成本留档
        db.expire_all()
        assert db.get(InventoryDocument, inbound.id).status == "void"
        assert db.get(InventoryDocument, outbound.id).status == "void"
        assert reverse_out.status == "confirmed" and reverse_in.status == "confirmed"
        assert reverse_out.confirmed_by == user_id and reverse_out.operator_id == user_id
        assert inbound.doc_no.startswith("RK") and len(inbound.doc_no) == 14
        assert outbound.doc_no.startswith("CK")
        assert reverse_out.doc_no.startswith("RK")
        assert reverse_in.doc_no.startswith("CK")

        outbound_items = db.scalars(
            select(InventoryDocumentItem).where(
                InventoryDocumentItem.document_id == outbound.id
            )
        ).all()
        assert [(i.quantity, i.unit_cost) for i in outbound_items] == [(40, Decimal("9.99"))]
        reverse_out_items = db.scalars(
            select(InventoryDocumentItem).where(
                InventoryDocumentItem.document_id == reverse_out.id
            )
        ).all()
        assert [(i.quantity, i.unit_cost) for i in reverse_out_items] == [(40, Decimal("9.99"))]
        reverse_in_items = db.scalars(
            select(InventoryDocumentItem).where(
                InventoryDocumentItem.document_id == reverse_in.id
            )
        ).all()
        assert [(i.quantity, i.unit_cost) for i in reverse_in_items] == [
            (100, Decimal("12.50"))
        ]

    # ---------------- 对账：余额 = 流水净和 = 逐笔 running balance ----------------
    with engine.connect() as conn:
        balance = conn.execute(
            text("SELECT quantity FROM inventory_balances WHERE sku_id = :sku"),
            {"sku": sku_id},
        ).scalar_one()
        movement_sum = conn.execute(
            text("SELECT COALESCE(SUM(delta), 0) FROM stock_movements WHERE sku_id = :sku"),
            {"sku": sku_id},
        ).scalar_one()
        assert balance == 3 and movement_sum == 3

        running_bad = conn.execute(
            text(
                """
                SELECT count(*) FROM (
                    SELECT SUM(delta) OVER (ORDER BY id) AS running, balance_after
                    FROM stock_movements WHERE sku_id = :sku
                ) t WHERE running <> balance_after
                """
            ),
            {"sku": sku_id},
        ).scalar_one()
        assert running_bad == 0

        negative = conn.execute(
            text("SELECT count(*) FROM inventory_balances WHERE quantity < 0")
        ).scalar_one()
        assert negative == 0

        # 每张单据：流水净额 == 当前明细的有符号合计（含改单更正）
        doc_net_bad = conn.execute(
            text(
                """
                WITH m AS (
                    SELECT document_id, sku_id, SUM(delta) AS net
                    FROM stock_movements WHERE document_id IS NOT NULL
                    GROUP BY document_id, sku_id
                ), i AS (
                    SELECT it.document_id, it.sku_id, SUM(it.quantity) AS qty,
                           CASE WHEN d.doc_type IN ('inbound', 'adjust_in') THEN 1 ELSE -1 END AS sign
                    FROM inventory_document_items it
                    JOIN inventory_documents d ON d.id = it.document_id
                    GROUP BY it.document_id, it.sku_id, d.doc_type
                )
                SELECT count(*) FROM m FULL JOIN i USING (document_id, sku_id)
                WHERE COALESCE(m.net, 0) <> COALESCE(i.sign * i.qty, 0)
                """
            )
        ).scalar_one()
        assert doc_net_bad == 0

        # 每张单据的流水条数不得少于明细条数（改单会多出更正流水）
        fewer_moves = conn.execute(
            text(
                """
                SELECT count(*) FROM (
                    SELECT d.id
                    FROM inventory_documents d
                    LEFT JOIN inventory_document_items it ON it.document_id = d.id
                    LEFT JOIN stock_movements m ON m.document_id = d.id
                    GROUP BY d.id
                    HAVING count(DISTINCT m.id) < count(DISTINCT it.id)
                ) t
                """
            )
        ).scalar_one()
        assert fewer_moves == 0

        # 全量流水 7 条：入库 1 + 出库 2（含 1 条更正）+ 盘盈 1 + 盘亏 1 + 两张反向单各 1
        assert conn.execute(text("SELECT count(*) FROM stock_movements")).scalar_one() == 7

    # ---------------- append-only：UPDATE / DELETE / TRUNCATE 均被触发器拒绝 ----------------
    for statement in (
        "UPDATE stock_movements SET delta = delta",
        "DELETE FROM stock_movements",
        "TRUNCATE stock_movements",
    ):
        with pytest.raises(Exception) as denied:
            with engine.begin() as conn:
                conn.exec_driver_sql(statement)
        assert "append-only" in str(denied.value)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM stock_movements")).scalar_one() == 7
