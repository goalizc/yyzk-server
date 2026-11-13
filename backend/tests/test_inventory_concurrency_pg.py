"""PG 并发回归：同一张单据并发冲正只能成功一次（审查 B2）。

默认跳过；需要显式提供一次性 PostgreSQL 库：

    PG_TEST_DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db \
      .venv/bin/python -m pytest backend/tests/test_inventory_concurrency_pg.py -q

测试在目标库内建独立 schema，结束时 DROP SCHEMA ... CASCADE，不会碰已有表。
SQLite 单测不支持行锁，因此这条只能跑在 PostgreSQL 上。
"""

from __future__ import annotations

import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.database import Base
from app.models import InventoryDocument, InventorySku, InventoryWarehouse, StockMovement, User, UserRole
from app.services.inventory import (
    DocumentInput,
    ItemInput,
    create_document,
    current_balance,
    reverse_document,
)

PG_URL = os.getenv("PG_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL, reason="需要 PG_TEST_DATABASE_URL 指向一次性 PostgreSQL 库"
)


@pytest.fixture()
def engine():
    schema = f"inv_test_{uuid.uuid4().hex[:8]}"
    engine = create_engine(PG_URL, connect_args={"options": f"-csearch_path={schema}"})
    with engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
        Base.metadata.create_all(conn)
    try:
        yield engine
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
        engine.dispose()


def _seed(engine) -> tuple[int, int, int, int]:
    """建一条已过账入库单，返回 (doc_id, user_id, sku_id, warehouse_id)。"""
    with Session(engine) as db:
        user = User(
            username="concurrent_op",
            password_hash="x",
            real_name="并发测试",
            roles=[UserRole(role="super_admin")],
        )
        warehouse = InventoryWarehouse(code="DEFAULT", name="默认仓")
        db.add_all([user, warehouse])
        db.commit()
        sku = InventorySku(sku_no="WL-1", name="物资", warehouse_id=warehouse.id)
        db.add(sku)
        db.commit()
        doc = create_document(
            db,
            DocumentInput(
                doc_type="inbound",
                warehouse_id=warehouse.id,
                items=(ItemInput(sku_id=sku.id, quantity=10),),
            ),
            user,
        )
        db.commit()
        return doc.id, user.id, sku.id, warehouse.id


def test_concurrent_reverse_only_succeeds_once(engine) -> None:
    doc_id, user_id, sku_id, warehouse_id = _seed(engine)
    barrier = threading.Barrier(2)
    results: list[str] = []

    def worker() -> None:
        with Session(engine) as db:
            user = db.get(User, user_id)
            barrier.wait(timeout=5)
            try:
                reverse_document(db, doc_id, user, remark="并发冲正")
                db.commit()
                results.append("ok")
            except BusinessError as exc:
                db.rollback()
                results.append(exc.code)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    # 行锁 + 状态复核：一个成功，另一个必然看到 void
    assert sorted(results) == ["DOCUMENT_ALREADY_VOIDED", "ok"]

    with Session(engine) as db:
        assert db.get(InventoryDocument, doc_id).status == "void"
        reverse_count = db.scalar(
            select(func.count())
            .select_from(InventoryDocument)
            .where(InventoryDocument.doc_type == "outbound")
        )
        assert reverse_count == 1
        assert current_balance(db, sku_id, warehouse_id) == 0
        assert sum(db.scalars(select(StockMovement.delta)).all()) == 0
