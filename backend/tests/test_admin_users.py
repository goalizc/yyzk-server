"""用户管理：列表、新建、修改与重置密码。"""

from tests.conftest import auth_headers, login, make_user


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


def test_auditor_cannot_create_user(client, db):
    headers = _headers(client, db, role="auditor")

    response = client.post(
        "/api/admin/users",
        json={"username": "x", "real_name": "x", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    )

    assert response.status_code == 403
