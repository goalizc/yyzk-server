from app.core.permissions import TICKET_READ, TICKET_WRITE
from tests.conftest import auth_headers, login, make_user


def test_login_returns_permissions(client, db):
    make_user(db, username="agent1", role="agent")

    body = login(client, "agent1")

    assert set(body["permissions"]) == {"ticket:read", "ticket:write", "fault:read"}


def test_me_returns_live_permissions(client, db):
    user = make_user(db, username="agent1", role="agent")
    headers = auth_headers(login(client, "agent1")["access_token"])

    user.role = "supervisor"
    db.commit()

    body = client.get("/api/auth/me", headers=headers).json()
    assert "stats:read" in body["permissions"]
    assert TICKET_READ in body["permissions"]
    assert TICKET_WRITE in body["permissions"]
