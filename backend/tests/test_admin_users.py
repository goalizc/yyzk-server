"""用户管理：列表、新建、修改与重置密码。"""

from datetime import datetime, timedelta, timezone

from tests.conftest import auth_headers, login, make_line, make_user


def _headers(client, db, role="super_admin"):
    make_user(db, username=f"u_{role}", role=role)
    return auth_headers(login(client, f"u_{role}")["access_token"])


def test_create_list_update_user(client, db):
    headers = _headers(client, db)

    created = client.post(
        "/api/admin/users",
        json={
            "username": "wangwei",
            "real_name": "王伟",
            "password": "Init@12345",
            "role": "agent",
            "product_lines": [],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    listed = client.get("/api/admin/users", headers=headers).json()
    assert any(item["username"] == "wangwei" for item in listed["items"])

    updated = client.put(
        f"/api/admin/users/{user_id}",
        json={"real_name": "王伟伟", "role": "supervisor"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "supervisor"


def test_duplicate_username(client, db):
    headers = _headers(client, db)
    payload = {
        "username": "wangwei", "real_name": "王伟", "password": "Init@12345",
        "role": "agent", "product_lines": [],
    }
    client.post("/api/admin/users", json=payload, headers=headers)

    response = client.post("/api/admin/users", json=payload, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "USERNAME_DUPLICATED"


def test_update_username_normalized_and_usable_for_login(client, db):
    headers = _headers(client, db)
    created = client.post(
        "/api/admin/users",
        json={"username": "wangwei", "real_name": "王伟", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    ).json()

    updated = client.put(
        f"/api/admin/users/{created['id']}",
        json={"username": "WangWei2"},
        headers=headers,
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["username"] == "wangwei2"
    assert login(client, "wangwei2", "Init@12345")["user"]["username"] == "wangwei2"
    old = client.post(
        "/api/auth/login", json={"username": "wangwei", "password": "Init@12345"}
    )
    assert old.status_code == 401


def test_update_username_conflict_keeps_original(client, db):
    headers = _headers(client, db)
    first = client.post(
        "/api/admin/users",
        json={"username": "a", "real_name": "甲", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    ).json()
    second = client.post(
        "/api/admin/users",
        json={"username": "b", "real_name": "乙", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    ).json()
    assert first["username"] == "a"

    response = client.put(
        f"/api/admin/users/{second['id']}",
        json={"username": "A"},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "USERNAME_DUPLICATED"
    users = {item["id"]: item for item in client.get("/api/admin/users", headers=headers).json()["items"]}
    assert users[second["id"]]["username"] == "b"


def test_update_username_blank_rejected(client, db):
    headers = _headers(client, db)
    created = client.post(
        "/api/admin/users",
        json={"username": "wangwei", "real_name": "王伟", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    ).json()

    response = client.put(
        f"/api/admin/users/{created['id']}",
        json={"username": "   "},
        headers=headers,
    )

    assert response.status_code == 422


def test_admin_can_rename_self_and_token_stays_valid(client, db):
    make_user(db, username="boss")
    headers = auth_headers(login(client, "boss")["access_token"])
    me = client.get("/api/auth/me", headers=headers).json()["user"]

    response = client.put(
        f"/api/admin/users/{me['id']}",
        json={"username": "boss2"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["username"] == "boss2"
    assert client.get("/api/auth/me", headers=headers).status_code == 200


def test_username_is_case_insensitive(client, db):
    headers = _headers(client, db)

    created = client.post(
        "/api/admin/users",
        json={"username": "WangWei", "real_name": "王伟", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["username"] == "wangwei"

    duplicated = client.post(
        "/api/admin/users",
        json={"username": "wangwei", "real_name": "王伟", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    )
    assert duplicated.status_code == 409
    assert duplicated.json()["code"] == "USERNAME_DUPLICATED"


def test_duplicate_product_line_rejected(client, db):
    headers = _headers(client, db)
    line = make_line(db)

    response = client.post(
        "/api/admin/users",
        json={
            "username": "wangwei",
            "real_name": "王伟",
            "password": "Init@12345",
            "role": "agent",
            "product_lines": [{"line_id": line.id}, {"line_id": line.id}],
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "LINE_DUPLICATED"


def test_cannot_disable_or_demote_self(client, db):
    make_user(db, username="boss")
    headers = auth_headers(login(client, "boss")["access_token"])
    me = client.get("/api/auth/me", headers=headers).json()["user"]

    assert client.put(
        f"/api/admin/users/{me['id']}", json={"is_active": False}, headers=headers
    ).status_code == 400
    assert client.put(
        f"/api/admin/users/{me['id']}", json={"role": "agent"}, headers=headers
    ).status_code == 400


def test_last_super_admin_guard_rejects_when_none_left(db):
    from app.api.admin_users import _ensure_other_super_admin
    from app.core.exceptions import BusinessError

    only = make_user(db, username="boss")

    try:
        _ensure_other_super_admin(db, only.id)
    except BusinessError as exc:
        assert exc.code == "LAST_SUPER_ADMIN"
    else:
        raise AssertionError("应当拒绝")


def test_reset_password_returns_once_and_works(client, db):
    headers = _headers(client, db)
    created = client.post(
        "/api/admin/users",
        json={"username": "wangwei", "real_name": "王伟", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    ).json()

    body = client.post(f"/api/admin/users/{created['id']}/reset-password", headers=headers).json()

    assert len(body["password"]) == 12
    assert login(client, "wangwei", body["password"])["user"]["username"] == "wangwei"


def test_reset_password_revokes_old_token(client, db):
    headers = _headers(client, db)
    created = client.post(
        "/api/admin/users",
        json={"username": "wangwei", "real_name": "王伟", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    ).json()
    old_token = login(client, "wangwei", "Init@12345")["access_token"]

    body = client.post(
        f"/api/admin/users/{created['id']}/reset-password", headers=headers
    ).json()

    expired = client.get("/api/auth/me", headers=auth_headers(old_token))
    assert expired.status_code == 401
    assert expired.json()["code"] == "AUTH_TOKEN_EXPIRED"

    new_token = login(client, "wangwei", body["password"])["access_token"]
    assert client.get("/api/auth/me", headers=auth_headers(new_token)).status_code == 200


def test_list_users_includes_active_grant_count(client, db):
    headers = _headers(client, db)
    created = client.post(
        "/api/admin/users",
        json={"username": "wangwei", "real_name": "王伟", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    ).json()
    assert created["active_grant_count"] == 0

    expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    grant = client.post(
        f"/api/admin/users/{created['id']}/grants",
        json={"permission": "stats:read", "expires_at": expires, "reason": "临时看板"},
        headers=headers,
    ).json()

    listed = client.get("/api/admin/users", headers=headers).json()
    item = next(row for row in listed["items"] if row["id"] == created["id"])
    assert item["active_grant_count"] == 1

    client.delete(f"/api/admin/users/{created['id']}/grants/{grant['id']}", headers=headers)

    listed = client.get("/api/admin/users", headers=headers).json()
    item = next(row for row in listed["items"] if row["id"] == created["id"])
    assert item["active_grant_count"] == 0


def test_auditor_cannot_create_user(client, db):
    headers = _headers(client, db, role="auditor")

    response = client.post(
        "/api/admin/users",
        json={"username": "x", "real_name": "x", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    )

    assert response.status_code == 403
