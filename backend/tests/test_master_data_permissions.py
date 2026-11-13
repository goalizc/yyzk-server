"""产品/零件/产品线主数据写权限：product_planner 可写，supervisor 只读。"""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, login, make_user


def _headers(client: TestClient, db, username: str, role: str) -> dict:
    make_user(db, username=username, role=role)
    return auth_headers(login(client, username)["access_token"])


def test_product_planner_can_write_master_data(client: TestClient, db) -> None:
    headers = _headers(client, db, "planner_api", "product_planner")

    line = client.post(
        "/api/admin/product-lines", json={"name": "计划线"}, headers=headers
    )
    assert line.status_code == 201, line.text

    product = client.post(
        "/api/admin/products",
        json={"name": "计划产品", "model": "PLAN-1", "line_id": line.json()["id"]},
        headers=headers,
    )
    assert product.status_code == 201, product.text

    part = client.post(
        "/api/admin/parts",
        json={
            "product_id": product.json()["id"],
            "name": "计划零件",
            "part_no": "P-PLAN-1",
        },
        headers=headers,
    )
    assert part.status_code == 201, part.text


def test_supervisor_cannot_write_master_data(client: TestClient, db) -> None:
    admin = _headers(client, db, "master_admin", "super_admin")
    line = client.post(
        "/api/admin/product-lines", json={"name": "只读线"}, headers=admin
    ).json()
    product = client.post(
        "/api/admin/products",
        json={"name": "只读产品", "model": "RO-1", "line_id": line["id"]},
        headers=admin,
    ).json()

    supervisor = _headers(client, db, "supervisor_ro", "supervisor")

    assert (
        client.post(
            "/api/admin/product-lines", json={"name": "越权线"}, headers=supervisor
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/products",
            json={"name": "越权产品", "model": "RO-2", "line_id": line["id"]},
            headers=supervisor,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/parts",
            json={"product_id": product["id"], "name": "越权零件"},
            headers=supervisor,
        ).status_code
        == 403
    )
