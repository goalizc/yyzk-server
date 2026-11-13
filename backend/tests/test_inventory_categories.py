"""进销存：分类主数据 + SKU 多分类 / 多产品筛选（任务卡 #24）。

文件名带 `inventory_` 前缀防 pytest 重名静默覆盖。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import InventoryWarehouse, Part, Product, ProductLine
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


def test_category_crud_and_duplicate(client: TestClient, db) -> None:
    headers = _headers(client, db)
    # 新建
    r = client.post(f"{BASE}/categories", json={"name": "螺丝"}, headers=headers)
    assert r.status_code == 201, r.text
    cat = r.json()
    assert cat["name"] == "螺丝" and cat["is_active"] is True
    # 重名 -> 409
    dup = client.post(f"{BASE}/categories", json={"name": "螺丝"}, headers=headers)
    assert dup.status_code == 409 and dup.json()["code"] == "CATEGORY_NAME_DUPLICATED"
    # 列表
    listed = client.get(f"{BASE}/categories", headers=headers).json()
    assert listed["total"] == 1
    # 编辑（备注 + 停用）
    upd = client.put(
        f"{BASE}/categories/{cat['id']}",
        json={"remark": "紧固件", "is_active": False},
        headers=headers,
    )
    assert upd.status_code == 200
    assert upd.json()["remark"] == "紧固件" and upd.json()["is_active"] is False


def test_sku_multi_category_and_filter(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    c1 = client.post(f"{BASE}/categories", json={"name": "螺丝"}, headers=headers).json()
    c2 = client.post(f"{BASE}/categories", json={"name": "电机"}, headers=headers).json()

    sku = client.post(
        f"{BASE}/skus",
        json={
            "sku_no": "WL-1",
            "name": "多分类件",
            "warehouse_id": wh.id,
            "category_ids": [c1["id"], c2["id"]],
        },
        headers=headers,
    )
    assert sku.status_code == 201, sku.text
    body = sku.json()
    assert {c["name"] for c in body["categories"]} == {"螺丝", "电机"}

    # 按分类筛选：两个分类都能筛到该 SKU
    assert (
        client.get(f"{BASE}/skus", params={"category_id": c1["id"]}, headers=headers).json()["total"]
        == 1
    )
    assert (
        client.get(f"{BASE}/skus", params={"category_id": c2["id"]}, headers=headers).json()["total"]
        == 1
    )
    # 不存在的分类 -> 0
    assert (
        client.get(f"{BASE}/skus", params={"category_id": 9999}, headers=headers).json()["total"]
        == 0
    )
    # 更新为只保留 c2
    upd = client.put(
        f"{BASE}/skus/{body['id']}", json={"category_ids": [c2["id"]]}, headers=headers
    ).json()
    assert {c["id"] for c in upd["categories"]} == {c2["id"]}
    assert (
        client.get(f"{BASE}/skus", params={"category_id": c1["id"]}, headers=headers).json()["total"]
        == 0
    )


def test_sku_product_filter(client: TestClient, db) -> None:
    headers = _headers(client, db)
    wh = _warehouse(db)
    line = ProductLine(name="植保")
    db.add(line)
    db.commit()
    db.refresh(line)
    prod = Product(name="植保机A", model="ZB-A", line_id=line.id)
    db.add(prod)
    db.commit()
    db.refresh(prod)

    sku = client.post(
        f"{BASE}/skus",
        json={
            "sku_no": "WL-P",
            "name": "配件P",
            "warehouse_id": wh.id,
            "product_ids": [prod.id],
        },
        headers=headers,
    )
    assert sku.status_code == 201, sku.text
    assert {p["id"] for p in sku.json()["products"]} == {prod.id}

    assert (
        client.get(f"{BASE}/skus", params={"product_id": prod.id}, headers=headers).json()["total"]
        == 1
    )
    assert (
        client.get(f"{BASE}/skus", params={"product_id": 99999}, headers=headers).json()["total"]
        == 0
    )


def test_document_list_filter_by_product(client: TestClient, db) -> None:
    """入库 / 出库列表按 SKU 关联产品筛选（与分类筛选可叠加）。"""
    headers = _headers(client, db)
    wh = _warehouse(db)
    cat = client.post(f"{BASE}/categories", json={"name": "滤芯"}, headers=headers).json()

    line = ProductLine(name="植保线")
    db.add(line)
    db.commit()
    db.refresh(line)
    p1 = Product(name="植保机A", model="ZB-A", line_id=line.id)
    p2 = Product(name="植保机B", model="ZB-B", line_id=line.id)
    db.add_all([p1, p2])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)

    sku1 = client.post(
        f"{BASE}/skus",
        json={
            "sku_no": "WL-D1",
            "name": "只属产品A",
            "warehouse_id": wh.id,
            "product_ids": [p1.id],
            "category_ids": [cat["id"]],
        },
        headers=headers,
    ).json()
    sku2 = client.post(
        f"{BASE}/skus",
        json={
            "sku_no": "WL-D2",
            "name": "只属产品B",
            "warehouse_id": wh.id,
            "product_ids": [p2.id],
        },
        headers=headers,
    ).json()

    def _inbound(sku_id: int) -> str:
        resp = client.post(
            f"{BASE}/inbound-orders",
            json={"warehouse_id": wh.id, "items": [{"sku_id": sku_id, "quantity": 5}]},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["doc_no"]

    doc1 = _inbound(sku1["id"])
    doc2 = _inbound(sku2["id"])

    def _list(**params) -> dict:
        return client.get(f"{BASE}/inbound-orders", params=params, headers=headers).json()

    only_p1 = _list(product_id=p1.id)
    assert only_p1["total"] == 1 and only_p1["items"][0]["doc_no"] == doc1
    assert _list(product_id=p2.id)["items"][0]["doc_no"] == doc2
    # 分类筛选叠加：产品 B 的单据不含该分类 → 0；产品 A 命中 → 1
    assert _list(product_id=p1.id, category_id=cat["id"])["total"] == 1
    assert _list(product_id=p2.id, category_id=cat["id"])["total"] == 0
    assert _list(product_id=99999)["total"] == 0
    # 出库列表同样支持该参数（此处只验参数可用、不报 422）
    assert client.get(
        f"{BASE}/outbound-orders", params={"product_id": p1.id}, headers=headers
    ).status_code == 200


def test_refs_endpoints_available_to_clerk(client: TestClient, db) -> None:
    """建 SKU 的「关联产品 / 零件」下拉：仓管没有 product:read / part:read，
    必须能通过库存域 /refs/* 拿到，否则两个下拉恒为空。"""
    line = ProductLine(name="植保线")
    db.add(line)
    db.commit()
    db.refresh(line)
    prod = Product(name="植保机A", model="ZB-A", line_id=line.id)
    db.add(prod)
    db.commit()
    db.refresh(prod)
    db.add(Part(product_id=prod.id, name="隔膜泵", part_no="P-01"))
    db.commit()

    make_user(db, username="clerk", role="warehouse_clerk")
    headers = auth_headers(login(client, username="clerk")["access_token"])

    products = client.get(f"{BASE}/refs/products", headers=headers)
    assert products.status_code == 200, products.text
    assert {"id": prod.id, "name": "植保机A", "model": "ZB-A"} in products.json()

    parts = client.get(
        f"{BASE}/refs/parts", params={"product_id": prod.id}, headers=headers
    )
    assert parts.status_code == 200, parts.text
    assert [(p["name"], p["part_no"]) for p in parts.json()] == [("隔膜泵", "P-01")]

    # 省略 product_id：一次返回全部零件，并带产品名（避免前端按产品 N+1 请求）
    all_parts = client.get(f"{BASE}/refs/parts", headers=headers)
    assert all_parts.status_code == 200, all_parts.text
    assert [(p["name"], p["product_name"]) for p in all_parts.json()] == [("隔膜泵", "植保机A")]

    # 产品不存在 -> 404（否则前端会把空列表当成"这个产品没有零件"）
    assert (
        client.get(f"{BASE}/refs/parts", params={"product_id": 9999}, headers=headers).status_code
        == 404
    )

    # 反向：一线客服没有 inventory:sku:read，不该借这两个端点读主数据
    make_user(db, username="agent1", role="agent")
    agent_headers = auth_headers(login(client, username="agent1")["access_token"])
    denied = client.get(f"{BASE}/refs/products", headers=agent_headers)
    assert denied.status_code == 403 and denied.json()["code"] == "PERMISSION_DENIED"
