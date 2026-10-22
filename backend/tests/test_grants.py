"""临时授权发放/收回与产品线整体替换。"""

from datetime import datetime, timedelta, timezone

from app.core.permissions import effective_permissions
from app.models import ProductLine, UserProductLine
from tests.conftest import auth_headers, login, make_user


def _admin_headers(client, db):
    make_user(db, username="boss")
    return auth_headers(login(client, "boss")["access_token"])


def _make_agent(db):
    return make_user(db, username="agent1", role="agent")


def test_grant_adds_permission_with_closure(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    response = client.post(
        f"/api/admin/users/{agent.id}/grants",
        json={"permission": "fault:write", "expires_at": expires, "reason": "临时接手知识库"},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    perms = effective_permissions(db, agent)
    assert {"fault:write", "fault:read", "product:read", "part:read", "upload:write"} <= perms


def test_grant_user_write_rejected(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    response = client.post(
        f"/api/admin/users/{agent.id}/grants",
        json={"permission": "user:write", "expires_at": expires, "reason": "提权"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PERMISSION"


def test_grant_past_expiry_rejected(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)

    response = client.post(
        f"/api/admin/users/{agent.id}/grants",
        json={
            "permission": "stats:read",
            "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            "reason": "过期",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_revoke_grant(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    grant = client.post(
        f"/api/admin/users/{agent.id}/grants",
        json={
            "permission": "stats:read",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "reason": "临时",
        },
        headers=headers,
    ).json()

    assert client.delete(
        f"/api/admin/users/{agent.id}/grants/{grant['id']}", headers=headers
    ).status_code == 200
    assert "stats:read" not in effective_permissions(db, agent)


def test_inactive_line_cannot_be_newly_assigned(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    line = ProductLine(name="停用线", is_active=False)
    db.add(line)
    db.commit()

    response = client.put(
        f"/api/admin/users/{agent.id}/product-lines",
        json=[{"line_id": line.id, "expires_at": None}],
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "LINE_INACTIVE"


def test_existing_inactive_line_can_be_kept(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    line = ProductLine(name="停用线", is_active=False)
    db.add(line)
    db.flush()
    db.add(UserProductLine(user_id=agent.id, line_id=line.id))
    db.commit()

    response = client.put(
        f"/api/admin/users/{agent.id}/product-lines",
        json=[{"line_id": line.id, "expires_at": None}],
        headers=headers,
    )

    assert response.status_code == 200, response.text


def test_replace_product_lines(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    line = ProductLine(name="扫地机")
    db.add(line)
    db.commit()

    response = client.put(
        f"/api/admin/users/{agent.id}/product-lines",
        json=[{"line_id": line.id, "expires_at": None}],
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["product_lines"][0]["name"] == "扫地机"
