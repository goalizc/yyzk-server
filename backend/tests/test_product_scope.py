"""产品写操作受产品线可见性约束：LINES 角色不能碰其它产品线的产品。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Product, ProductLine, UserPermissionGrant, UserProductLine
from tests.conftest import auth_headers, login, make_user


def _setup(db):
    line_a = ProductLine(name="A线")
    line_b = ProductLine(name="B线")
    db.add_all([line_a, line_b])
    db.flush()
    product_b = Product(line_id=line_b.id, name="B线产品", model="B1")
    db.add(product_b)
    db.commit()
    return line_a, line_b, product_b


def _agent_with_product_write(client, db):
    line_a, line_b, product_b = _setup(db)
    agent = make_user(db, username="agent1", role="agent")
    db.add(UserProductLine(user_id=agent.id, line_id=line_a.id))
    db.add(
        UserPermissionGrant(
            user_id=agent.id,
            permission="product:write",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            reason="临时维护产品",
        )
    )
    db.commit()
    headers = auth_headers(login(client, "agent1")["access_token"])
    return agent, headers, line_a, line_b, product_b


def test_cannot_edit_product_of_other_line(client, db) -> None:
    _, headers, _, _, product_b = _agent_with_product_write(client, db)

    response = client.put(
        f"/api/admin/products/{product_b.id}", json={"name": "改名"}, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_cannot_move_product_into_own_line(client, db) -> None:
    _, headers, line_a, _, product_b = _agent_with_product_write(client, db)

    response = client.put(
        f"/api/admin/products/{product_b.id}",
        json={"line_id": line_a.id},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_cannot_create_product_in_other_line(client, db) -> None:
    _, headers, _, line_b, _ = _agent_with_product_write(client, db)

    response = client.post(
        "/api/admin/products",
        json={"name": "越权产品", "model": "X9", "line_id": line_b.id},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_can_create_product_in_own_line(client, db) -> None:
    _, headers, line_a, _, _ = _agent_with_product_write(client, db)

    response = client.post(
        "/api/admin/products",
        json={"name": "本线产品", "model": "A9", "line_id": line_a.id},
        headers=headers,
    )

    assert response.status_code == 201, response.text


def test_cannot_delete_product_of_other_line(client, db) -> None:
    _, headers, _, _, product_b = _agent_with_product_write(client, db)

    response = client.delete(f"/api/admin/products/{product_b.id}", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
