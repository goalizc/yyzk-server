"""产品线 CRUD 与产品关联（契约 §2）。"""

from tests.conftest import auth_headers, login, make_user


def _headers(client, db):
    make_user(db, username="admin")
    return auth_headers(login(client, "admin")["access_token"])


def test_create_and_list_line(client, db):
    headers = _headers(client, db)

    created = client.post(
        "/api/admin/product-lines", json={"name": "扫地机", "sort_order": 1}, headers=headers
    )
    assert created.status_code == 201
    body = client.get("/api/admin/product-lines", headers=headers).json()
    assert body["items"][0]["name"] == "扫地机"


def test_duplicate_line_name(client, db):
    headers = _headers(client, db)
    client.post("/api/admin/product-lines", json={"name": "扫地机"}, headers=headers)

    response = client.post("/api/admin/product-lines", json={"name": "扫地机"}, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "LINE_NAME_DUPLICATED"


def test_delete_line_referenced_by_product(client, db):
    headers = _headers(client, db)
    line = client.post("/api/admin/product-lines", json={"name": "扫地机"}, headers=headers).json()
    client.post(
        "/api/admin/products",
        json={"name": "扫地机器人", "model": "X1", "line_id": line["id"]},
        headers=headers,
    )

    response = client.delete(f"/api/admin/product-lines/{line['id']}", headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "DELETE_BLOCKED"


def test_product_requires_line(client, db):
    headers = _headers(client, db)

    response = client.post(
        "/api/admin/products", json={"name": "扫地机器人", "model": "X1"}, headers=headers
    )

    assert response.status_code == 422


def test_product_response_has_line_name(client, db):
    headers = _headers(client, db)
    line = client.post("/api/admin/product-lines", json={"name": "扫地机"}, headers=headers).json()

    product = client.post(
        "/api/admin/products",
        json={"name": "扫地机器人", "model": "X1", "line_id": line["id"]},
        headers=headers,
    ).json()

    assert product["line_id"] == line["id"]
    assert product["line_name"] == "扫地机"
    assert "category" not in product
