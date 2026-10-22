from datetime import datetime, timedelta, timezone

from app.core.permissions import (
    ALL_PERMISSIONS,
    LINES,
    TICKET_ASSIGN,
    TICKET_READ,
    TICKET_WRITE,
    USER_WRITE,
    data_scope,
    effective_permissions,
    expand,
    role_permissions,
)
from app.models import UserPermissionGrant
from tests.conftest import make_user


def test_role_matrix_is_closed():
    for role in ("super_admin", "supervisor", "agent", "auditor"):
        assert role_permissions(role) == expand(role_permissions(role))


def test_agent_permissions_exact():
    assert role_permissions("agent") == {"ticket:read", "ticket:write", "fault:read"}
    assert data_scope(type("U", (), {"role": "agent"})()) == LINES


def test_closure_pulls_in_dependencies():
    assert expand({TICKET_ASSIGN}) == {TICKET_ASSIGN, TICKET_READ, TICKET_WRITE}
    assert {"fault:read", "product:read", "part:read", "upload:write"} <= expand({"fault:write"})


def test_active_grant_is_added_and_expired_is_ignored(db):
    user = make_user(db, role="agent")
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            UserPermissionGrant(
                user_id=user.id,
                permission="stats:read",
                expires_at=now + timedelta(hours=1),
                reason="临时看看板",
            ),
            UserPermissionGrant(
                user_id=user.id,
                permission="user:read",
                expires_at=now - timedelta(hours=1),
                reason="已过期",
            ),
        ]
    )
    db.commit()

    perms = effective_permissions(db, user)
    assert "stats:read" in perms
    assert "user:read" not in perms
    assert TICKET_WRITE in perms


def test_revoked_grant_is_ignored(db):
    user = make_user(db, role="agent")
    db.add(
        UserPermissionGrant(
            user_id=user.id,
            permission="stats:read",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            reason="收回测试",
            revoked_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    assert "stats:read" not in effective_permissions(db, user)


def test_user_write_not_grantable():
    from app.core.permissions import grantable_permissions

    assert USER_WRITE not in grantable_permissions()
    assert grantable_permissions() == ALL_PERMISSIONS - {USER_WRITE}
