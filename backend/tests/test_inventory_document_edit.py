"""进销存：主管修改已生效入库 / 出库单（任务卡 #25）。

覆盖：净更正流水、明细整体替换、角色边界、已冲正拒绝、库存不足整单回滚。
文件名带 `inventory_` 前缀防 pytest 重名静默覆盖。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import InventoryWarehouse
from tests.conftest import auth_headers, login, make_user

BASE = "/api/admin/inventory"


def _headers(client: TestClient, db, *, role: str = "super_admin", username: str = "admin") -> dict:
    make_user(db, username=username, role=role)
    return auth_headers(login(client, username)["access_token"])


def _warehouse(db) -> InventoryWarehouse:
    row = InventoryWarehouse(code="DEFAULT", name="默认仓")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _sku(client: TestClient, headers: dict, warehouse_id: int, sku_no: str = "WL-0001") -> dict:
    response = client.post(
        f"{BASE}/skus",
        json={"sku_no": sku_no, "name": f"物资-{sku_no}", "warehouse_id": warehouse_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _document(
    client: TestClient,
    headers: dict,
    warehouse_id: int,
    items: list[dict],
    resource: str = "inbound-orders",
) -> dict:
    response = client.post(
        f"{BASE}/{resource}", json={"warehouse_id": warehouse_id, "items": items}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _qty(client: TestClient, headers: dict, sku_id: int) -> int:
    return client.get(f"{BASE}/skus/{sku_id}", headers=headers).json()["quantity"]


def test_manager_edits_inbound_quantity_and_net_movement(client: TestClient, db) -> None:
    headers = _headers(client, db, role="warehouse_manager", username="mgr")
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    doc = _document(client, headers, wh.id, [{"sku_id": sku["id"], "quantity": 10}])

    response = client.put(
        f"{BASE}/documents/{doc['id']}",
        json={"items": [{"sku_id": sku["id"], "quantity": 15}]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["quantity"] == 15
    assert _qty(client, headers, sku["id"]) == 15

    # 原流水保留 + 一条净更正流水（+5），不是重过账
    movements = client.get(f"{BASE}/movements", headers=headers).json()
    assert movements["total"] == 2
    assert sorted(row["delta"] for row in movements["items"]) == [5, 10]


def test_manager_edits_item_types(client: TestClient, db) -> None:
    headers = _headers(client, db, role="warehouse_manager", username="mgr")
    wh = _warehouse(db)
    sku_a = _sku(client, headers, wh.id, "WL-A")
    sku_b = _sku(client, headers, wh.id, "WL-B")
    doc = _document(client, headers, wh.id, [{"sku_id": sku_a["id"], "quantity": 8}])

    # 删掉 A、换成 B（数量 3）
    response = client.put(
        f"{BASE}/documents/{doc['id']}",
        json={"items": [{"sku_id": sku_b["id"], "quantity": 3}]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert [item["sku_id"] for item in response.json()["items"]] == [sku_b["id"]]
    assert _qty(client, headers, sku_a["id"]) == 0
    assert _qty(client, headers, sku_b["id"]) == 3


def test_clerk_cannot_edit_confirmed_document(client: TestClient, db) -> None:
    admin = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, admin, wh.id)
    doc = _document(client, admin, wh.id, [{"sku_id": sku["id"], "quantity": 4}])

    clerk = _headers(client, db, role="warehouse_clerk", username="clerk")
    response = client.put(
        f"{BASE}/documents/{doc['id']}",
        json={"items": [{"sku_id": sku["id"], "quantity": 5}]},
        headers=clerk,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_voided_document_cannot_be_edited(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    doc = _document(client, headers, wh.id, [{"sku_id": sku["id"], "quantity": 6}])

    assert client.post(
        f"{BASE}/documents/{doc['id']}/reverse", json={"remark": "登记错误"}, headers=headers
    ).status_code == 201

    response = client.put(
        f"{BASE}/documents/{doc['id']}",
        json={"items": [{"sku_id": sku["id"], "quantity": 7}]},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "DOCUMENT_ALREADY_VOIDED"


def test_outbound_edit_over_balance_rolls_back(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    _document(client, headers, wh.id, [{"sku_id": sku["id"], "quantity": 10}])
    outbound = _document(
        client, headers, wh.id, [{"sku_id": sku["id"], "quantity": 4}], "outbound-orders"
    )
    assert _qty(client, headers, sku["id"]) == 6

    # 4 -> 20 需要再扣 16，但只剩 6，整单回滚
    response = client.put(
        f"{BASE}/documents/{outbound['id']}",
        json={"items": [{"sku_id": sku["id"], "quantity": 20}]},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INSUFFICIENT_STOCK"
    # 明细与余额都没变
    detail = client.get(f"{BASE}/outbound-orders/{outbound['id']}", headers=headers).json()
    assert detail["items"][0]["quantity"] == 4
    assert _qty(client, headers, sku["id"]) == 6


def test_adjustment_cannot_be_edited(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    sku = _sku(client, headers, wh.id)
    created = client.post(
        f"{BASE}/adjustments",
        json={
            "warehouse_id": wh.id,
            "adjust_type": "in",
            "items": [{"sku_id": sku["id"], "quantity": 2}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    adjustment = created.json()

    response = client.put(
        f"{BASE}/documents/{adjustment['id']}",
        json={"items": [{"sku_id": sku["id"], "quantity": 3}]},
        headers=headers,
    )
    assert response.status_code == 400
    assert "入库单 / 出库单" in response.json()["detail"]
