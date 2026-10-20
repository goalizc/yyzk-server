"""登录与改密：错误码必须与 API 契约 §1 / §7 一致。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import User
from tests.conftest import DEFAULT_PASSWORD, auth_headers, login, make_user


def test_login_success_returns_token_and_user(client: TestClient, db) -> None:
    make_user(db)

    response = client.post("/api/auth/login", json={"username": "admin", "password": DEFAULT_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_at"].endswith("+08:00")
    assert body["user"] == {
        "id": 1,
        "username": "admin",
        "real_name": "系统管理员",
        "role": "admin",
    }


def test_login_updates_last_login_at(client: TestClient, db) -> None:
    user = make_user(db)
    assert user.last_login_at is None

    login(client)

    db.expire_all()
    refreshed = db.get(User, user.id)
    assert refreshed is not None and refreshed.last_login_at is not None


def test_login_wrong_password(client: TestClient, db) -> None:
    make_user(db)

    response = client.post("/api/auth/login", json={"username": "admin", "password": "WrongPwd@1"})

    assert response.status_code == 401
    assert response.json() == {"detail": "用户名或密码错误", "code": "AUTH_INVALID_CREDENTIALS"}


def test_login_unknown_user_uses_same_message(client: TestClient, db) -> None:
    response = client.post("/api/auth/login", json={"username": "ghost", "password": "Whatever@1"})

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID_CREDENTIALS"


def test_login_disabled_user(client: TestClient, db) -> None:
    make_user(db, is_active=False)

    response = client.post("/api/auth/login", json={"username": "admin", "password": DEFAULT_PASSWORD})

    assert response.status_code == 403
    assert response.json() == {"detail": "账号已停用", "code": "AUTH_USER_DISABLED"}


def test_login_empty_username_is_validation_error(client: TestClient, db) -> None:
    response = client.post("/api/auth/login", json={"username": "  ", "password": "x"})

    assert response.status_code == 422
    assert response.json() == {"detail": "请输入用户名", "code": "VALIDATION_ERROR"}


def test_password_change_requires_token(client: TestClient, db) -> None:
    response = client.put(
        "/api/auth/password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": "NewPwd@2026"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "登录已过期，请重新登录", "code": "AUTH_TOKEN_EXPIRED"}


def test_password_change_rejects_invalid_token(client: TestClient, db) -> None:
    response = client.put(
        "/api/auth/password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": "NewPwd@2026"},
        headers=auth_headers("not-a-jwt"),
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_TOKEN_EXPIRED"


def test_password_change_wrong_old_password(client: TestClient, db) -> None:
    make_user(db)
    token = login(client)["access_token"]

    response = client.put(
        "/api/auth/password",
        json={"old_password": "WrongOld@1", "new_password": "NewPwd@2026"},
        headers=auth_headers(token),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "原密码不正确", "code": "PASSWORD_INVALID"}


def test_password_change_same_as_old(client: TestClient, db) -> None:
    make_user(db)
    token = login(client)["access_token"]

    response = client.put(
        "/api/auth/password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
        headers=auth_headers(token),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "新密码不能与原密码相同", "code": "PASSWORD_SAME"}


def test_password_change_too_short(client: TestClient, db) -> None:
    make_user(db)
    token = login(client)["access_token"]

    response = client.put(
        "/api/auth/password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": "short"},
        headers=auth_headers(token),
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "新密码至少 8 位", "code": "VALIDATION_ERROR"}


def test_password_change_success_and_token_still_valid(client: TestClient, db) -> None:
    make_user(db)
    token = login(client)["access_token"]

    response = client.put(
        "/api/auth/password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": "NewPwd@2026"},
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "密码已修改"}

    # 新密码可登录，旧密码失效
    assert client.post("/api/auth/login", json={"username": "admin", "password": "NewPwd@2026"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "admin", "password": DEFAULT_PASSWORD}).status_code == 401

    # 契约：改密后不强制下线，旧 token 继续有效（用错的原密码换取 400 证明鉴权通过）
    still_valid = client.put(
        "/api/auth/password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": "Another@2026"},
        headers=auth_headers(token),
    )
    assert still_valid.status_code == 400
    assert still_valid.json()["code"] == "PASSWORD_INVALID"


def test_password_stored_as_bcrypt_hash(client: TestClient, db) -> None:
    user = make_user(db)
    token = login(client)["access_token"]

    client.put(
        "/api/auth/password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": "NewPwd@2026"},
        headers=auth_headers(token),
    )

    db.expire_all()
    refreshed = db.get(User, user.id)
    assert refreshed is not None
    assert refreshed.password_hash.startswith("$2")
    assert "NewPwd@2026" not in refreshed.password_hash


def test_expired_token_rejected(client: TestClient, db) -> None:
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.config import get_settings

    make_user(db)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "1",
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
        },
        get_settings().jwt_secret,
        algorithm=get_settings().jwt_algorithm,
    )

    response = client.put(
        "/api/auth/password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": "NewPwd@2026"},
        headers=auth_headers(token),
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_TOKEN_EXPIRED"


def test_disabled_user_token_rejected(client: TestClient, db) -> None:
    user = make_user(db)
    token = login(client)["access_token"]

    user.is_active = False
    db.commit()

    response = client.put(
        "/api/auth/password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": "NewPwd@2026"},
        headers=auth_headers(token),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "账号已停用", "code": "AUTH_USER_DISABLED"}


def test_login_rejects_password_over_bcrypt_limit(client: TestClient, db) -> None:
    # bcrypt 只取前 72 字节，超长密码必须在入口拒绝，不能静默截断后放行
    make_user(db)

    response = client.post("/api/auth/login", json={"username": "admin", "password": "A" * 73})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "72" in response.json()["detail"]
