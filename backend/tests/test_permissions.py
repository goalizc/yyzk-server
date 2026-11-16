from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.permissions import (
    ALL,
    ALL_PERMISSIONS,
    INVENTORY_ADJUST_WRITE,
    INVENTORY_COST_READ,
    LINES,
    PART_WRITE,
    PRODUCT_LINE_WRITE,
    PRODUCT_WRITE,
    TICKET_ASSIGN,
    TICKET_READ,
    TICKET_WRITE,
    USER_WRITE,
    data_scope,
    effective_permissions,
    expand,
    role_permissions,
    role_scope,
)
from app.models import UserPermissionGrant
from tests.conftest import make_user


def test_role_matrix_is_closed():
    for role in (
        "super_admin",
        "supervisor",
        "product_planner",
        "warehouse_clerk",
        "warehouse_manager",
        "agent",
        "auditor",
    ):
        assert role_permissions(role) == expand(role_permissions(role))


def test_product_planner_is_master_writer():
    perms = role_permissions("product_planner")
    assert {
        "product:read",
        "product:write",
        "part:read",
        "part:write",
        "product_line:read",
        "product_line:write",
    } <= perms
    # 主数据角色不碰售后、库存、用户、审计
    assert perms.isdisjoint(
        {
            "ticket:read",
            "ticket:write",
            "fault:read",
            "fault:write",
            "inventory:sku:read",
            "user:read",
            "audit:read",
        }
    )


def test_supervisor_master_read_only():
    perms = role_permissions("supervisor")
    assert {"product:read", "part:read", "product_line:read"} <= perms
    assert {PRODUCT_WRITE, PART_WRITE, PRODUCT_LINE_WRITE}.isdisjoint(perms)


def test_agent_permissions_exact():
    assert role_permissions("agent") == {"ticket:read", "ticket:write", "fault:read"}
    agent = SimpleNamespace(roles=[SimpleNamespace(role="agent")])
    assert data_scope(agent) == LINES


def test_multi_role_permissions_and_scope_are_union(db):
    user = make_user(db, username="multi", roles=["agent", "warehouse_clerk"])

    perms = effective_permissions(db, user)
    # 一线客服 + 仓管录入员的并集：两边权限都要生效
    assert {"ticket:read", "ticket:write", "inventory:sku:read"} <= perms
    # 但数据范围是分域的：仓管的 ALL 只针对库存，
    # 不能把工单可见范围从「本产品线」抬成「全部产品线」
    assert data_scope(user) == LINES
    assert role_scope("warehouse_clerk") == ALL


def test_warehouse_only_user_keeps_narrow_ticket_scope(db):
    # 纯仓管没有工单权限；即便将来误挂上工单码，范围也只能是最窄的
    user = make_user(db, username="wh-only", roles=["warehouse_clerk"])
    assert data_scope(user) == LINES
    assert role_scope("warehouse_clerk") == ALL


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


def test_sensitive_permissions_not_grantable():
    from app.core.permissions import grantable_permissions

    hidden = {
        USER_WRITE,
        INVENTORY_ADJUST_WRITE,
        INVENTORY_COST_READ,
        PRODUCT_WRITE,
        PART_WRITE,
        PRODUCT_LINE_WRITE,
    }
    grantable = grantable_permissions()
    assert hidden.isdisjoint(grantable)
    assert grantable == ALL_PERMISSIONS - hidden
