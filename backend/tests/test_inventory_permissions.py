"""进销存权限矩阵与依赖闭包专项验收（PRD 任务卡 #2）。

纯函数校验，不需要 db；与需求定案稿 §2.1 / §2.2 / §2.3 / §2.4 一一对应。
"""

from app.core.permissions import (
    ALL,
    ALL_PERMISSIONS,
    INVENTORY_ADJUST_WRITE,
    INVENTORY_COST_READ,
    INVENTORY_DOC_EDIT,
    INVENTORY_EXPORT,
    INVENTORY_INBOUND_READ,
    INVENTORY_INBOUND_WRITE,
    INVENTORY_MOVEMENT_READ,
    INVENTORY_OUTBOUND_READ,
    INVENTORY_OUTBOUND_WRITE,
    INVENTORY_SKU_READ,
    INVENTORY_SKU_WRITE,
    expand,
    grantable_permissions,
    role_permissions,
    role_scope,
)

INVENTORY_CODES = frozenset(
    {
        INVENTORY_SKU_READ,
    INVENTORY_SKU_WRITE,
    INVENTORY_INBOUND_READ,
    INVENTORY_INBOUND_WRITE,
    INVENTORY_OUTBOUND_READ,
    INVENTORY_OUTBOUND_WRITE,
    INVENTORY_MOVEMENT_READ,
    INVENTORY_ADJUST_WRITE,
    INVENTORY_EXPORT,
    INVENTORY_COST_READ,
    INVENTORY_DOC_EDIT,
}
)

ROLES = ("super_admin", "supervisor", "warehouse_clerk", "warehouse_manager", "agent", "auditor")


def test_eleven_inventory_codes_registered():
    assert len(INVENTORY_CODES) == 11
    assert INVENTORY_CODES <= ALL_PERMISSIONS


def test_role_matrix_is_closed_for_all_six_roles():
    for role in ROLES:
        assert role_permissions(role) == expand(role_permissions(role)), role


def test_super_admin_and_supervisor_have_full_inventory():
    assert INVENTORY_CODES <= role_permissions("super_admin")
    assert INVENTORY_CODES <= role_permissions("supervisor")


def test_clerk_is_pure_inventory_without_adjust():
    perms = role_permissions("warehouse_clerk")
    assert INVENTORY_CODES - {INVENTORY_ADJUST_WRITE, INVENTORY_COST_READ, INVENTORY_DOC_EDIT} <= perms
    assert INVENTORY_ADJUST_WRITE not in perms
    assert INVENTORY_COST_READ not in perms
    assert INVENTORY_DOC_EDIT not in perms
    # 对售后模块零权限：长期不与工单/知识库挂钩。
    # 建 SKU 选产品 / 零件走库存域自己的 /refs/* 端点，不靠 product:read。
    assert perms.isdisjoint({"ticket:read", "fault:read", "product:read", "stats:read"})


def test_manager_has_clerk_perms_plus_doc_edit():
    perms = role_permissions("warehouse_manager")
    # 主管继承录入员全部库存权限
    assert INVENTORY_SKU_WRITE in perms
    assert INVENTORY_INBOUND_WRITE in perms
    assert INVENTORY_OUTBOUND_WRITE in perms
    # 且独有「改已生效单据」权限
    assert INVENTORY_DOC_EDIT in perms
    assert INVENTORY_ADJUST_WRITE not in perms
    assert INVENTORY_COST_READ not in perms


def test_auditor_inventory_is_read_only_plus_export():
    perms = role_permissions("auditor")
    assert {
        INVENTORY_SKU_READ,
        INVENTORY_INBOUND_READ,
        INVENTORY_OUTBOUND_READ,
        INVENTORY_MOVEMENT_READ,
        INVENTORY_EXPORT,
    } <= perms
    assert perms.isdisjoint(
        {
            INVENTORY_SKU_WRITE,
            INVENTORY_INBOUND_WRITE,
            INVENTORY_OUTBOUND_WRITE,
            INVENTORY_ADJUST_WRITE,
            INVENTORY_COST_READ,
        }
    )


def test_agent_has_no_inventory_access():
    assert role_permissions("agent").isdisjoint(INVENTORY_CODES)


def test_cost_read_not_assigned_to_business_roles():
    # 只登记、不分配：super_admin / supervisor 的 ALL_PERMISSIONS 天然含它，
    # 但业务角色不能拿到，且没有任何端点 require 它（见 PRD §3.6）。
    for role in ("warehouse_clerk", "agent", "auditor"):
        assert INVENTORY_COST_READ not in role_permissions(role)


def test_inventory_data_scope_is_all():
    # 纯物资 part_id 为空，没有产品线可判；库存域统一 ALL，不继承 LINES
    for role in ("super_admin", "supervisor", "warehouse_clerk", "auditor"):
        assert role_scope(role) == ALL


def test_dependencies_expand_to_reads():
    assert {
        INVENTORY_SKU_READ,
        INVENTORY_INBOUND_READ,
        INVENTORY_OUTBOUND_READ,
        INVENTORY_MOVEMENT_READ,
    } <= expand({INVENTORY_EXPORT})
    assert {
        INVENTORY_MOVEMENT_READ,
        INVENTORY_INBOUND_READ,
        INVENTORY_OUTBOUND_READ,
        INVENTORY_SKU_READ,
    } <= expand({INVENTORY_ADJUST_WRITE})
    assert INVENTORY_SKU_READ in expand({INVENTORY_COST_READ})
    assert INVENTORY_SKU_READ in expand({INVENTORY_INBOUND_WRITE})


def test_grantable_excludes_three_sensitive_codes():
    grantable = grantable_permissions()
    for code in ("user:write", INVENTORY_ADJUST_WRITE, INVENTORY_COST_READ):
        assert code not in grantable
    # 其余 9 个库存码仍可临时授予
    assert INVENTORY_CODES - {INVENTORY_ADJUST_WRITE, INVENTORY_COST_READ} <= grantable
