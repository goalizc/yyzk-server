"""进销存 18 个端点验收（PRD 任务卡 #4 / §12）。

文件名带 `inventory_` 前缀防 pytest 重名静默覆盖。
PG 专属的行锁与 append-only 触发器留任务卡 #9 真机验证。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import InventoryWarehouse
from tests.conftest import auth_headers, login, make_user

BASE = "/api/admin/inventory"


def _headers(client: TestClient, db) -> dict:
    make_user(db)
    return auth_headers(login(client)["access_token"])


def _warehouse(db) -> InventoryWarehouse:
    row = InventoryWarehouse(code="DEFAULT", name="默认仓")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _sku(
    client: TestClient,
    headers: dict,
    warehouse_id: int,
    sku_no: str = "WL-0001",
    **kwargs,
) -> dict:
    payload = {
        "sku_no": sku_no,
        "name": f"物资-{sku_no}",
        "warehouse_id": warehouse_id,
        "min_stock": 2,
        **kwargs,
    }
    response = client.post(f"{BASE}/skus", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _document(
    client: TestClient,
    headers: dict,
    warehouse_id: int,
    sku_id: int,
    quantity: int,
    resource: str = "inbound-orders",
    **extra,
):
    body = {
        "warehouse_id": warehouse_id,
        "items": [{"sku_id": sku_id, "quantity": quantity}],
        **extra,
    }
    return client.post(f"{BASE}/{resource}", json=body, headers=headers)


# ---------------------------------------------------------------- 契约 / 权限


def test_requires_auth_and_warehouse_page(client: TestClient, db) -> None:
    assert client.get(f"{BASE}/warehouses").status_code == 401

    headers = _headers(client, db)
    _warehouse(db)
    response = client.get(f"{BASE}/warehouses", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"total", "page", "page_size", "items"}
    assert body["total"] == 1
    assert body["items"][0]["code"] == "DEFAULT"


def test_page_size_over_100_is_422(client: TestClient, db) -> None:
    headers = _headers(client, db)
    assert client.get(
        f"{BASE}/skus", params={"page_size": 101}, headers=headers
    ).status_code == 422


def test_agent_has_no_inventory_access(client: TestClient, db) -> None:
    make_user(db, username="agent1", role="agent")
    headers = auth_headers(login(client, "agent1")["access_token"])
    _warehouse(db)
    response = client.get(f"{BASE}/skus", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------- SKU


def test_sku_crud_duplicate_and_soft_delete(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    assert sku["sku_no"] == "WL-0001" and sku["quantity"] == 0

    listed = client.get(f"{BASE}/skus", headers=headers).json()
    assert listed["total"] == 1
    detail = client.get(f"{BASE}/skus/{sku['id']}", headers=headers).json()
    assert detail["recent_movements"] == []

    updated = client.put(
        f"{BASE}/skus/{sku['id']}",
        json={"name": "改名", "min_stock": 5},
        headers=headers,
    ).json()
    assert updated["name"] == "改名" and updated["min_stock"] == 5

    duplicate = client.post(
        f"{BASE}/skus",
        json={"sku_no": "WL-0001", "name": "重复", "warehouse_id": wh.id},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "SKU_NO_DUPLICATED"

    assert client.delete(f"{BASE}/skus/{sku['id']}", headers=headers).status_code == 200
    inactive = client.get(
        f"{BASE}/skus", params={"is_active": "false"}, headers=headers
    ).json()
    assert inactive["total"] == 1


def test_pure_material_stocked_via_api(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id, sku_no="WL-PURE", part_id=None)
    assert sku["part_id"] is None and sku["part_name"] is None

    response = _document(client, headers, wh.id, sku["id"], 3)
    assert response.status_code == 201
    assert client.get(f"{BASE}/skus/{sku['id']}", headers=headers).json()["quantity"] == 3


def test_sku_in_use_cannot_be_disabled(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    assert _document(client, headers, wh.id, sku["id"], 5).status_code == 201

    response = client.delete(f"{BASE}/skus/{sku['id']}", headers=headers)
    assert response.status_code == 409
    assert response.json()["code"] == "SKU_IN_USE"


def test_sku_in_use_cannot_be_disabled_via_update(client: TestClient, db) -> None:
    """审查 B1：编辑表单的 is_active 不能绕过 DELETE 的 SKU_IN_USE 规则。

    否则被单据引用的 SKU 会被停用，随后原单冲正/改单都会被
    INVENTORY_SKU_INACTIVE 拒绝，台账不可更正。
    """
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    assert _document(client, headers, wh.id, sku["id"], 5).status_code == 201

    response = client.put(
        f"{BASE}/skus/{sku['id']}", json={"is_active": False}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SKU_IN_USE"
    assert client.get(f"{BASE}/skus/{sku['id']}", headers=headers).json()["is_active"] is True


def test_unit_cost_is_write_only_across_all_responses(client: TestClient, db) -> None:
    """§3.6 防回归：单价可写，但列表/详情/单据明细/导出一律不返回。"""
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id, unit_cost="12.34")
    assert "unit_cost" not in sku

    response = client.post(
        f"{BASE}/inbound-orders",
        json={
            "warehouse_id": wh.id,
            "items": [{"sku_id": sku["id"], "quantity": 3, "unit_cost": "35.50"}],
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert "unit_cost" not in response.text
    detail = client.get(
        f"{BASE}/inbound-orders/{response.json()['id']}", headers=headers
    ).json()
    assert "unit_cost" not in detail["items"][0]

    for export_type in ("balance", "movement"):
        csv_text = client.get(
            f"{BASE}/export", params={"type": export_type}, headers=headers
        ).text
        assert "35.50" not in csv_text
        assert "unit_cost" not in csv_text


# ---------------------------------------------------------------- 单据 / 过账


def test_inbound_outbound_balance_and_movements(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)

    inbound = _document(client, headers, wh.id, sku["id"], 10)
    assert inbound.status_code == 201
    body = inbound.json()
    assert body["status"] == "confirmed" and body["confirmed_by"] is not None
    assert body["doc_no"].startswith("RK") and len(body["doc_no"]) == 14
    assert body["items"][0]["sku_no"] == "WL-0001"

    outbound = _document(client, headers, wh.id, sku["id"], 4, "outbound-orders")
    assert outbound.status_code == 201 and outbound.json()["doc_no"].startswith("CK")
    assert client.get(f"{BASE}/skus/{sku['id']}", headers=headers).json()["quantity"] == 6

    movements = client.get(f"{BASE}/movements", headers=headers).json()
    assert movements["total"] == 2
    assert {row["delta"] for row in movements["items"]} == {10, -4}
    assert {row["doc_status"] for row in movements["items"]} == {"confirmed"}

    pages = client.get(f"{BASE}/inbound-orders", headers=headers).json()
    assert set(pages) == {"total", "page", "page_size", "items"} and pages["total"] == 1


def test_insufficient_stock_rolls_back_whole_document(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    assert _document(client, headers, wh.id, sku["id"], 10).status_code == 201

    response = _document(client, headers, wh.id, sku["id"], 15, "outbound-orders")
    assert response.status_code == 400
    assert response.json()["code"] == "INSUFFICIENT_STOCK"
    assert client.get(f"{BASE}/skus/{sku['id']}", headers=headers).json()["quantity"] == 10
    assert client.get(f"{BASE}/movements", headers=headers).json()["total"] == 1


def test_empty_items_and_inactive_sku_rejected(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)

    empty = client.post(
        f"{BASE}/inbound-orders",
        json={"warehouse_id": wh.id, "items": []},
        headers=headers,
    )
    assert empty.status_code == 400 and empty.json()["code"] == "INVENTORY_ITEM_EMPTY"

    assert client.put(
        f"{BASE}/skus/{sku['id']}", json={"is_active": False}, headers=headers
    ).status_code == 200
    inactive = _document(client, headers, wh.id, sku["id"], 1)
    assert inactive.status_code == 400
    assert inactive.json()["code"] == "INVENTORY_SKU_INACTIVE"


def test_document_type_mismatch_is_404(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    doc_id = _document(client, headers, wh.id, sku["id"], 5).json()["id"]
    assert client.get(f"{BASE}/outbound-orders/{doc_id}", headers=headers).status_code == 404


def test_adjustment_and_reverse(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    doc = _document(client, headers, wh.id, sku["id"], 10).json()

    adjustment = client.post(
        f"{BASE}/adjustments",
        json={
            "warehouse_id": wh.id,
            "adjust_type": "in",
            "items": [{"sku_id": sku["id"], "quantity": 2}],
        },
        headers=headers,
    )
    assert adjustment.status_code == 201
    assert adjustment.json()["doc_type"] == "adjust_in"
    assert adjustment.json()["doc_no"].startswith("PD")
    assert client.get(f"{BASE}/skus/{sku['id']}", headers=headers).json()["quantity"] == 12

    reverse = client.post(
        f"{BASE}/documents/{doc['id']}/reverse",
        json={"remark": "登记错误"},
        headers=headers,
    )
    assert reverse.status_code == 201 and reverse.json()["doc_type"] == "outbound"
    assert client.get(
        f"{BASE}/inbound-orders/{doc['id']}", headers=headers
    ).json()["status"] == "void"
    again = client.post(
        f"{BASE}/documents/{doc['id']}/reverse",
        json={"remark": "再来一次"},
        headers=headers,
    )
    assert again.status_code == 400
    assert again.json()["code"] == "DOCUMENT_ALREADY_VOIDED"

    # 流水带单据状态：原单 void 后前端应隐藏冲正按钮，反向单仍可操作
    moves = client.get(f"{BASE}/movements", headers=headers).json()["items"]
    status_by_doc = {row["doc_no"]: row["doc_status"] for row in moves}
    assert status_by_doc[doc["doc_no"]] == "void"
    assert status_by_doc[reverse.json()["doc_no"]] == "confirmed"


# ---------------------------------------------------------------- 低库存 / 汇总 / 导出 / 时间


def test_low_stock_and_summary(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id, min_stock=5)
    assert _document(client, headers, wh.id, sku["id"], 2).status_code == 201

    low = client.get(f"{BASE}/low-stock", headers=headers).json()
    assert low["total"] == 1 and low["items"][0]["shortage"] == 3
    assert low["items"][0]["quantity"] == 2

    summary = client.get(f"{BASE}/summary", headers=headers).json()
    assert summary["sku_count"] == 1
    assert summary["low_stock_count"] == 1
    assert summary["inbound_this_month"] == 1
    assert summary["outbound_this_month"] == 0


def test_export_both_types_have_bom_and_no_cost(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    assert _document(client, headers, wh.id, sku["id"], 7).status_code == 201

    balance = client.get(f"{BASE}/export", params={"type": "balance"}, headers=headers)
    assert balance.status_code == 200 and balance.text.startswith("\ufeff")
    assert "SKU编码" in balance.text and "WL-0001" in balance.text

    movement = client.get(f"{BASE}/export", params={"type": "movement"}, headers=headers)
    assert movement.status_code == 200 and movement.text.startswith("\ufeff")
    assert "变动量" in movement.text and "RK" in movement.text


def test_export_declares_truncation(client: TestClient, db, monkeypatch) -> None:
    """审查 S6：超过导出上限时必须显式告知，不能静默只给前 N 行。"""
    from app.api import admin_inventory_movements

    monkeypatch.setattr(admin_inventory_movements, "_EXPORT_LIMIT", 1)

    headers = _headers(client, db)
    wh = _warehouse(db)
    sku_a = _sku(client, headers, wh.id, "WL-A")
    sku_b = _sku(client, headers, wh.id, "WL-B")
    assert _document(client, headers, wh.id, sku_a["id"], 1).status_code == 201
    assert _document(client, headers, wh.id, sku_b["id"], 1).status_code == 201

    balance = client.get(f"{BASE}/export", params={"type": "balance"}, headers=headers)
    assert balance.headers.get("x-export-truncated") == "1"
    assert balance.headers.get("x-export-total") == "2"

    movement = client.get(f"{BASE}/export", params={"type": "movement"}, headers=headers)
    assert movement.headers.get("x-export-truncated") == "1"
    assert movement.headers.get("x-export-total") == "2"


def test_time_fields_are_plus_08(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    assert sku["created_at"].endswith("+08:00")
    assert sku["updated_at"].endswith("+08:00")
