"""产品与零件：公开接口 + 后台 CRUD（契约 §2、§3）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import Fault, Part, Product
from tests.conftest import auth_headers, login, make_line, make_user


def make_product(db, name: str = "智能扫地机器人", model: str = "X1", **kwargs) -> Product:
    product = Product(name=name, model=model, line_id=make_line(db).id, **kwargs)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def make_part(db, product: Product, name: str = "主刷模组", **kwargs) -> Part:
    part = Part(product_id=product.id, name=name, **kwargs)
    db.add(part)
    db.commit()
    db.refresh(part)
    return part


def make_fault(db, product: Product, part: Part, title: str = "开机无反应") -> Fault:
    fault = Fault(product_id=product.id, part_id=part.id, title=title)
    db.add(fault)
    db.commit()
    db.refresh(fault)
    return fault


def admin_headers(client: TestClient, db) -> dict:
    make_user(db)
    return auth_headers(login(client)["access_token"])


# ---------------------------------------------------------------- 公开接口


def test_public_products_only_active_sorted(client: TestClient, db) -> None:
    make_product(db, model="X2", sort_order=2)
    make_product(db, name="净化器", model="A2", sort_order=1)
    make_product(db, name="已下架", model="OLD", is_active=False, sort_order=0)

    response = client.get("/api/products")

    assert response.status_code == 200
    body = response.json()
    assert [item["model"] for item in body] == ["A2", "X2"]
    assert set(body[0]) == {"id", "name", "model", "line_id", "line_name", "sort_order"}


def test_public_parts_cascade_by_product(client: TestClient, db) -> None:
    product = make_product(db)
    other = make_product(db, name="净化器", model="A2")
    make_part(db, product, name="主刷模组", group_name="动力系统", sort_order=2)
    make_part(db, product, name="水箱模组", group_name="清洁系统", sort_order=1)
    make_part(db, other, name="滤芯", group_name="过滤系统")

    response = client.get(f"/api/products/{product.id}/parts")

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body] == ["主刷模组", "水箱模组"]  # group_name 升序
    assert set(body[0]) == {"id", "part_no", "name", "group_name", "sort_order"}


def test_public_parts_product_not_found(client: TestClient, db) -> None:
    response = client.get("/api/products/9999/parts")

    assert response.status_code == 404
    assert response.json() == {"detail": "产品不存在", "code": "NOT_FOUND"}


# ---------------------------------------------------------------- 后台产品


def test_admin_products_requires_token(client: TestClient, db) -> None:
    response = client.get("/api/admin/products")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_TOKEN_EXPIRED"


def test_admin_products_pagination_and_fault_count(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db, model="X1", sort_order=1)
    make_product(db, name="净化器", model="A2", sort_order=2)

    part = make_part(db, product)
    make_fault(db, product, part)
    make_fault(db, product, part, title="充电不亮")

    response = client.get("/api/admin/products?page=1&page_size=1", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 1
    assert len(body["items"]) == 1
    first = body["items"][0]
    assert first["model"] == "X1"
    assert first["fault_count"] == 2
    assert set(first) == {
        "id", "name", "model", "line_id", "line_name", "description", "is_active",
        "sort_order", "fault_count", "created_at", "updated_at",
    }
    assert first["created_at"].endswith("+08:00")


def test_admin_products_keyword_and_active_filter(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    make_product(db, name="智能扫地机器人", model="X1")
    make_product(db, name="净化器", model="A2", is_active=False)

    by_keyword = client.get("/api/admin/products?keyword=净化", headers=headers).json()
    assert by_keyword["total"] == 1
    assert by_keyword["items"][0]["model"] == "A2"

    by_model = client.get("/api/admin/products?keyword=x1", headers=headers).json()
    assert by_model["total"] == 1

    inactive = client.get("/api/admin/products?is_active=false", headers=headers).json()
    assert inactive["total"] == 1
    assert inactive["items"][0]["model"] == "A2"


def test_admin_products_page_size_limit(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.get("/api/admin/products?page_size=101", headers=headers)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_create_product(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    line = make_line(db)

    response = client.post(
        "/api/admin/products",
        json={
            "name": "智能扫地机器人",
            "model": "X1",
            "line_id": line.id,
            "description": "",
            "is_active": True,
            "sort_order": 3,
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["model"] == "X1"
    assert body["line_id"] == line.id
    assert body["line_name"] == line.name
    assert body["sort_order"] == 3
    assert body["fault_count"] == 0


def test_create_product_duplicated_model(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    make_product(db, model="X1")

    response = client.post(
        "/api/admin/products",
        json={"name": "另一个", "model": "X1", "line_id": make_line(db).id},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "型号 X1 已存在", "code": "MODEL_DUPLICATED"}


def test_update_product_partial(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db, model="X1", sort_order=0)

    response = client.put(
        f"/api/admin/products/{product.id}", json={"sort_order": 9}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["sort_order"] == 9
    assert response.json()["model"] == "X1"  # 未传字段不变


def test_update_product_model_conflict(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    make_product(db, model="X1")
    other = make_product(db, name="净化器", model="A2")

    response = client.put(
        f"/api/admin/products/{other.id}", json={"model": "X1"}, headers=headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "MODEL_DUPLICATED"


def test_update_product_not_found(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.put("/api/admin/products/9999", json={"name": "x"}, headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_delete_product_blocked_by_parts_and_faults(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    make_part(db, product, name="水箱模组")
    make_fault(db, product, part)

    response = client.delete(f"/api/admin/products/{product.id}", headers=headers)

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "DELETE_BLOCKED"
    assert "2 个零件" in body["detail"] and "1 条故障" in body["detail"]


def test_delete_product_success(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)

    response = client.delete(f"/api/admin/products/{product.id}", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert db.get(Product, product.id) is None


def test_delete_product_not_found(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.delete("/api/admin/products/9999", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------- 后台零件


def test_admin_parts_requires_product_id(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.get("/api/admin/parts", headers=headers)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_admin_parts_list_with_fault_count(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product, part_no="P-X1-001", group_name="动力系统")
    make_part(db, product, name="水箱模组", group_name="清洁系统", sort_order=1)
    make_fault(db, product, part)

    response = client.get(f"/api/admin/parts?product_id={product.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    first = body["items"][0]
    assert set(first) == {
        "id", "product_id", "part_no", "name", "group_name", "sort_order", "fault_count",
    }
    counts = {item["name"]: item["fault_count"] for item in body["items"]}
    assert counts == {"主刷模组": 1, "水箱模组": 0}


def test_create_part_product_not_found(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.post(
        "/api/admin/parts", json={"product_id": 9999, "name": "主刷模组"}, headers=headers
    )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_create_part(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)

    response = client.post(
        "/api/admin/parts",
        json={
            "product_id": product.id,
            "part_no": "P-X1-001",
            "name": "主刷模组",
            "group_name": "动力系统",
            "sort_order": 1,
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["product_id"] == product.id
    assert response.json()["fault_count"] == 0


def test_update_part(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product, sort_order=1)

    response = client.put(
        f"/api/admin/parts/{part.id}", json={"name": "主刷模组（新）"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "主刷模组（新）"
    assert response.json()["sort_order"] == 1


def test_delete_part_blocked_by_faults(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    make_fault(db, product, part)

    response = client.delete(f"/api/admin/parts/{part.id}", headers=headers)

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "DELETE_BLOCKED"
    assert "1 条故障" in body["detail"]


def test_delete_part_success(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)

    response = client.delete(f"/api/admin/parts/{part.id}", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert db.get(Part, part.id) is None


def test_keyword_wildcards_are_escaped(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    make_product(db, name="100%纯棉拖布", model="M100")
    make_product(db, name="100X纯棉拖布", model="M101")

    body = client.get("/api/admin/products?keyword=100%25", headers=headers).json()

    assert body["total"] == 1  # % 被当字面量，不是通配符
    assert body["items"][0]["model"] == "M100"
