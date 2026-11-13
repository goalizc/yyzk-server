# Product Master Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把产品/零件/产品线主数据的唯一业务写权限收口到新增的 `product_planner`（产品计划）角色，售后与物资只保留只读引用，并把主数据从售后菜单中分组出来。

**Architecture:** 复用现有 `product:read/write`、`part:read/write`、`product_line:read/write` 权限码，不新增权限码；新增一个角色 `product_planner` 作为唯一常规写者，`super_admin` 保留 break-glass 全部权限。售后主管移除三个主数据写码，页面已有 `hasPermission` 门禁会自动变成只读；仓管继续走库存域 `/inventory/refs/*`。主数据写权限同时从临时授权清单中排除。多角色（`user_roles`）不在本计划内，作为后续独立改造；本计划保持单角色模型。

**Tech Stack:** FastAPI + SQLAlchemy + PostgreSQL + Pytest；Vue 3 + Element Plus + Vitest + Playwright。

> **执行约定（重要）：** 进销存功能基线已提交为 `4473b43`。本计划在执行过程中**不自动逐个 Task commit**（用户只授权了开始前的基线提交）；每个任务以“测试通过 / 检查通过”为检查点，改动保留在工作区。若用户中途要求提交，再按 Task 粒度拆分 commit。

---

## File Structure

**后端**
- Modify `backend/app/core/permissions.py` — 新角色、supervisor 去写、grantable 排除。
- Modify `backend/app/schemas/user.py` — `ROLE_VALUES` 加 `product_planner`。
- Create `deploy/migrations/008_product_planner.sql` — 角色 CHECK 放宽。
- Modify `deploy/schema.sql` — 角色 CHECK、迁移登记、修订号。
- Modify `backend/tests/test_permissions.py` — 角色矩阵与 grantable 基线。
- Modify `backend/tests/test_inventory_permissions.py` — grantable 排除与角色列表。
- Modify `backend/tests/test_grants.py` — 主数据写不可临时授予。
- Modify `backend/tests/test_admin_users.py` — 新角色可建/可改。
- Create `backend/tests/test_master_data_permissions.py` — 主数据接口写权限（planner 可写 / supervisor 403）。

**前端**
- Modify `frontend/src/utils/roles.js` — 新角色 key、主数据分组、产品线分配排除。
- Create `frontend/src/utils/roles.spec.js` — 角色分组与 `usesProductLines` 单测。
- Modify `frontend/src/locales/{zh-CN,en-US}/common.js` — 角色名与角色分组。
- Modify `frontend/src/locales/{zh-CN,en-US}/admin.js` — 菜单分组标题。
- Modify `frontend/src/views/admin/Layout.vue` — 侧栏菜单分组。
- Modify `frontend/src/views/admin/Layout.spec.js` — 分组断言。
- Modify `frontend/src/views/admin/users/UserList.spec.js` — 7 角色与主数据分组。
- Modify `frontend/src/views/admin/inventory/SkuList.vue` — 产品/零件缺档提示。
- Modify `frontend/src/views/admin/faults/FaultEdit.vue` — 产品/零件缺档提示。
- Modify `frontend/src/locales/{zh-CN,en-US}/admin-inventory.js` — 缺档提示文案。
- Modify `frontend/src/locales/{zh-CN,en-US}/admin-fault.js` — 缺档提示文案。

**文档**
- Modify `docs/01-需求设计/进销存模块PRD与数据模型设计.md`
- Modify `docs/02-技术设计/API接口契约.md`
- Modify `deploy/schema.sql` 头部修订说明

---

## Task 1: 后端角色矩阵（product_planner 唯一写者，supervisor 只读）

**Files:**
- Modify: `backend/app/core/permissions.py`
- Test: `backend/tests/test_permissions.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_permissions.py` 顶部导入补上三个常量：

```python
from app.core.permissions import (
    ALL_PERMISSIONS,
    INVENTORY_ADJUST_WRITE,
    INVENTORY_COST_READ,
    LINES,
    PART_WRITE,
    PRODUCT_LINE_WRITE,
    PRODUCT_WRITE,
    TICKET_ASSIGN,
    TICKET_READ,
    USER_WRITE,
    effective_permissions,
    expand,
    role_permissions,
    role_scope,
)
```

在 `test_role_matrix_is_closed` 的角色元组中加入 `product_planner`：

```python
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
```

新增两个测试：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
.venv/bin/python -m pytest backend/tests/test_permissions.py -q
```
Expected: FAIL — `role_permissions("product_planner")` 抛 `KeyError`，且 supervisor 仍含三个写码。

- [ ] **Step 3: 最小实现**

修改 `backend/app/core/permissions.py`：

`ROLE_NAMES` 增加：

```python
ROLE_NAMES = {
    "super_admin": "超级管理员",
    "supervisor": "售后主管",
    "product_planner": "产品计划",
    "warehouse_clerk": "仓管录入员",
    "warehouse_manager": "仓管主管",
    "agent": "一线客服",
    "auditor": "只读审计",
}
```

在 `_INVENTORY_MANAGER` 附近增加主数据角色集合：

```python
# 主数据唯一业务写者：产品/零件/产品线。售后与物资只读引用。
# super_admin 仍保留全部权限作为 break-glass，不在此集合内。
_PRODUCT_MASTER = frozenset(
    {
        PRODUCT_READ,
        PRODUCT_WRITE,
        PART_READ,
        PART_WRITE,
        PRODUCT_LINE_READ,
        PRODUCT_LINE_WRITE,
    }
)
```

`_ROLE_PERMISSIONS` 改为：

```python
_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "super_admin": ALL_PERMISSIONS,
    # 售后主管保留主数据只读，不再写产品/零件/产品线
    "supervisor": ALL_PERMISSIONS
    - {
        USER_READ,
        USER_WRITE,
        PRODUCT_WRITE,
        PART_WRITE,
        PRODUCT_LINE_WRITE,
    },
    "product_planner": _PRODUCT_MASTER,
    "warehouse_clerk": _INVENTORY_CLERK,
    "warehouse_manager": _INVENTORY_MANAGER,
    "agent": frozenset({TICKET_READ, TICKET_WRITE, FAULT_READ}),
    "auditor": frozenset(
        {
            TICKET_READ,
            PRODUCT_READ,
            PART_READ,
            FAULT_READ,
            STATS_READ,
            USER_READ,
            PRODUCT_LINE_READ,
            AUDIT_READ,
        }
    )
    | _AUDITOR_INVENTORY,
}
```

`_DATA_SCOPE` 增加：

```python
_DATA_SCOPE: dict[str, str] = {
    "super_admin": ALL,
    "supervisor": ALL,
    "product_planner": ALL,
    "warehouse_clerk": ALL,
    "warehouse_manager": ALL,
    "agent": LINES,
    "auditor": ALL,
}
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```bash
.venv/bin/python -m pytest backend/tests/test_permissions.py -q
```
Expected: PASS。

- [ ] **Step 5: 检查点**

记录 `git diff backend/app/core/permissions.py backend/tests/test_permissions.py`，不提交，进入 Task 2。

---

## Task 2: 数据库角色 CHECK、schema 与用户白名单

**Files:**
- Create: `deploy/migrations/008_product_planner.sql`
- Modify: `deploy/schema.sql`
- Modify: `backend/app/schemas/user.py`
- Test: `backend/tests/test_admin_users.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_admin_users.py` 末尾新增：

```python
def test_product_planner_role_can_be_created_and_assigned(client, db):
    headers = _headers(client, db)

    created = client.post(
        "/api/admin/users",
        json={
            "username": "planner1",
            "real_name": "计划员",
            "password": "Init@12345",
            "role": "product_planner",
            "product_lines": [],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "product_planner"

    agent = client.post(
        "/api/admin/users",
        json={
            "username": "agent_for_planner",
            "real_name": "客服",
            "password": "Init@12345",
            "role": "agent",
            "product_lines": [],
        },
        headers=headers,
    ).json()
    updated = client.put(
        f"/api/admin/users/{agent['id']}",
        json={"role": "product_planner"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["role"] == "product_planner"
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
.venv/bin/python -m pytest backend/tests/test_admin_users.py::test_product_planner_role_can_be_created_and_assigned -q
```
Expected: FAIL — 422 `VALIDATION_ERROR`（`ROLE_VALUES` 不含新角色）。

- [ ] **Step 3: 实现 schema 与迁移**

修改 `backend/app/schemas/user.py`：

```python
ROLE_VALUES = (
    "super_admin",
    "supervisor",
    "product_planner",
    "agent",
    "auditor",
    "warehouse_clerk",
    "warehouse_manager",
)
```

新建 `deploy/migrations/008_product_planner.sql`：

```sql
-- 008_product_planner：产品/零件/产品线主数据唯一业务写者
-- 全部幂等，可被 deploy/scripts/migrate.py 重复执行。
-- 与 deploy/schema.sql v1.5 一一对应。
-- 注意：本文件内禁止出现百分号字符（psycopg2 占位符冲突）。

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN (
        'super_admin',
        'supervisor',
        'product_planner',
        'agent',
        'auditor',
        'warehouse_clerk',
        'warehouse_manager'
    ));

-- 主数据写改为不可临时授予：收回既有未过期授权，
-- 否则历史授权会继续给 supervisor/其他角色留下 product:write 等写入口。
UPDATE user_permission_grants
SET revoked_at = NOW()
WHERE permission IN ('product:write', 'part:write', 'product_line:write')
  AND revoked_at IS NULL
  AND (expires_at IS NULL OR expires_at > NOW());
```

修改 `deploy/schema.sql`：

1. 头部修订号改为：

```sql
-- 修订：v1.5  2026-11-13（产品主数据归属：新增 product_planner 角色）
--   v1.5 变更：users.role 增加 product_planner；该角色是产品/零件/产品线
--             主数据的唯一常规写者，售后与物资只读引用。
```

2. `users` 表角色 CHECK 改为：

```sql
                  CHECK (role IN (
                      'super_admin',
                      'supervisor',
                      'product_planner',
                      'agent',
                      'auditor',
                      'warehouse_clerk',
                      'warehouse_manager'
                  )),
```

3. 文件末尾追加：

```sql
INSERT INTO schema_migrations (version) VALUES ('008_product_planner');
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```bash
.venv/bin/python -m pytest backend/tests/test_admin_users.py -q
```
Expected: PASS。

- [ ] **Step 5: 检查点**

不提交，进入 Task 2B。

---

## Task 2B: 主数据接口写权限验收（product_planner 可写 / supervisor 403）

**Files:**
- Create: `backend/tests/test_master_data_permissions.py`

- [ ] **Step 1: 写验收测试**

新建 `backend/tests/test_master_data_permissions.py`：

```python
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
```

- [ ] **Step 2: 跑测试**

Run:
```bash
.venv/bin/python -m pytest backend/tests/test_master_data_permissions.py -q
```
Expected: 在 Task 1/2 完成后 PASS；若在权限改造前运行，`product_planner` 用例应失败（422/403），`supervisor` 用例应失败（201）。

- [ ] **Step 3: 检查点**

不提交，进入 Task 3。

---

## Task 3: 主数据写权限排除临时授权

**Files:**
- Modify: `backend/app/core/permissions.py`
- Modify: `backend/tests/test_permissions.py`
- Modify: `backend/tests/test_inventory_permissions.py`
- Modify: `backend/tests/test_grants.py`

- [ ] **Step 1: 写失败测试**

修改 `backend/tests/test_permissions.py` 的 `test_sensitive_permissions_not_grantable`：

```python
def test_sensitive_permissions_not_grantable():
    from app.core.permissions import grantable_permissions

    grantable = grantable_permissions()
    hidden = {
        USER_WRITE,
        INVENTORY_ADJUST_WRITE,
        INVENTORY_COST_READ,
        PRODUCT_WRITE,
        PART_WRITE,
        PRODUCT_LINE_WRITE,
    }
    assert hidden.isdisjoint(grantable)
    assert grantable == ALL_PERMISSIONS - hidden
```

修改 `backend/tests/test_inventory_permissions.py`：

```python
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
    PART_WRITE,
    PRODUCT_LINE_WRITE,
    PRODUCT_WRITE,
    expand,
    grantable_permissions,
    role_permissions,
    role_scope,
)
```

把 `ROLES` 改为 7 个角色，并把闭包测试改名：

```python
ROLES = (
    "super_admin",
    "supervisor",
    "product_planner",
    "warehouse_clerk",
    "warehouse_manager",
    "agent",
    "auditor",
)


def test_role_matrix_is_closed_for_all_seven_roles():
    for role in ROLES:
        assert role_permissions(role) == expand(role_permissions(role)), role


def test_product_planner_has_no_inventory_access():
    assert role_permissions("product_planner").isdisjoint(INVENTORY_CODES)
```

把 `test_grantable_excludes_three_sensitive_codes` 改名为 `test_grantable_excludes_sensitive_codes`，并改为：

```python
def test_grantable_excludes_sensitive_codes():
    grantable = grantable_permissions()
    for code in (
        "user:write",
        INVENTORY_ADJUST_WRITE,
        INVENTORY_COST_READ,
        PRODUCT_WRITE,
        PART_WRITE,
        PRODUCT_LINE_WRITE,
    ):
        assert code not in grantable
    # 其余 9 个库存码仍可临时授予
    assert INVENTORY_CODES - {INVENTORY_ADJUST_WRITE, INVENTORY_COST_READ} <= grantable
```

在 `backend/tests/test_grants.py` 新增：

```python
def test_grant_master_data_write_rejected(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    response = client.post(
        f"/api/admin/users/{agent.id}/grants",
        json={
            "permission": "product:write",
            "expires_at": expires,
            "reason": "临时改产品",
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PERMISSION"
```

并在 `test_grantable_permissions_endpoint_is_single_source` 的 hidden 列表中加入：

```python
    for hidden in (
        "user:write",
        "inventory:adjust:write",
        "inventory:cost:read",
        "product:write",
        "part:write",
        "product_line:write",
    ):
        assert hidden not in codes
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
.venv/bin/python -m pytest backend/tests/test_permissions.py backend/tests/test_grants.py backend/tests/test_inventory_permissions.py -q
```
Expected: FAIL — 三个主数据写码仍在 grantable 中；`product:write` 授权返回 201 而非 400。

- [ ] **Step 3: 实现排除**

修改 `backend/app/core/permissions.py` 的 `grantable_permissions()`：

```python
def grantable_permissions() -> frozenset[str]:
    """可临时授予的权限。

    永远排除：
    - `user:write`：临时授权会变成提权入口，可直接改角色；
    - `inventory:adjust:write`：冲正能凭空改账，不应带 expires_at / reason 临时发放；
    - `inventory:cost:read`：L1 只登记不启用、无端点使用；
    - `product:write` / `part:write` / `product_line:write`：
      主数据单写者，常规只能由 product_planner 角色持有；
      super_admin 的 break-glass 权限不通过临时授权转授。
    """
    return ALL_PERMISSIONS - {
        USER_WRITE,
        INVENTORY_ADJUST_WRITE,
        INVENTORY_COST_READ,
        PRODUCT_WRITE,
        PART_WRITE,
        PRODUCT_LINE_WRITE,
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```bash
.venv/bin/python -m pytest backend/tests/test_permissions.py backend/tests/test_grants.py backend/tests/test_inventory_permissions.py -q
```
Expected: PASS。

- [ ] **Step 5: 检查点**

不提交，进入 Task 4。

---

## Task 4: 前端角色名、角色分组与 product_planner

**Files:**
- Modify: `frontend/src/utils/roles.js`
- Create: `frontend/src/utils/roles.spec.js`
- Modify: `frontend/src/locales/zh-CN/common.js`
- Modify: `frontend/src/locales/en-US/common.js`
- Modify: `frontend/src/views/admin/users/UserList.spec.js`

- [ ] **Step 1: 写失败测试**

新建 `frontend/src/utils/roles.spec.js`：

```js
import { describe, expect, it } from 'vitest'
import { ROLE_GROUPS, ROLE_KEYS, ROLE_VALUES, usesProductLines } from './roles'

describe('roles', () => {
  it('product_planner 是主数据角色，且分组不漏角色', () => {
    expect(ROLE_KEYS.product_planner).toBe('common.role.product_planner')
    const flattened = ROLE_GROUPS.flatMap((group) => group.roles)
    expect(flattened.sort()).toEqual([...ROLE_VALUES].sort())
    const master = ROLE_GROUPS.find((group) => group.key === 'common.roleGroup.master')
    expect(master.roles).toEqual(['product_planner'])
  })

  it('product_planner 不参与产品线分配', () => {
    expect(usesProductLines('product_planner')).toBe(false)
    expect(usesProductLines('supervisor')).toBe(true)
  })
})
```

修改 `frontend/src/views/admin/users/UserList.spec.js`：

1. 分组测试的期望改为：

```js
    expect(dialogGroups.map((g) => g.label)).toEqual([
      '系统管理',
      '主数据',
      '售后角色',
      '仓管角色'
    ])
```

2. “6 个选项”测试标题与注释改为 7 个，并加入 `产品计划`：

```js
  it('新建用户弹窗的角色下拉有 7 个选项（曾因模板引用已删除的常量而变成空列表）', async () => {
    const wrapper = mountList()
    await flushPromises()

    const btn = wrapper.findAll('button').find((b) => b.text().includes('新建用户'))
    await btn.trigger('click')
    await flushPromises()

    // 七角色：super_admin / supervisor / product_planner / agent / auditor / warehouse_clerk / warehouse_manager
    // 「仓管」限定词不可省：supervisor 是售后主管，裸写「主管」两者分不清
    const roles = ['超级管理员', '产品计划', '售后主管', '一线客服', '只读审计', '仓管录入员', '仓管主管']
    const labels = wrapper
      .findAllComponents({ name: 'ElOption' })
      .map((c) => c.props('label'))
      .filter((l) => roles.includes(l))
    // 顶部筛选 + 弹窗各 7 个；弹窗为空列表时这里只有 7 → 立刻红
    expect(labels.length).toBe(14)
  })
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
cd frontend && npx vitest run src/utils/roles.spec.js src/views/admin/users/UserList.spec.js --reporter=dot
```
Expected: FAIL — 缺少 `product_planner` key/分组，分组标签仍为 3 个。

- [ ] **Step 3: 实现角色与文案**

修改 `frontend/src/utils/roles.js`：

```js
export const ROLE_KEYS = {
  super_admin: 'common.role.super_admin',
  supervisor: 'common.role.supervisor',
  product_planner: 'common.role.product_planner',
  warehouse_clerk: 'common.role.warehouse_clerk',
  warehouse_manager: 'common.role.warehouse_manager',
  agent: 'common.role.agent',
  auditor: 'common.role.auditor'
}

export const ROLE_GROUPS = [
  { key: 'common.roleGroup.system', roles: ['super_admin'] },
  { key: 'common.roleGroup.master', roles: ['product_planner'] },
  { key: 'common.roleGroup.service', roles: ['supervisor', 'agent', 'auditor'] },
  { key: 'common.roleGroup.warehouse', roles: ['warehouse_clerk', 'warehouse_manager'] }
]
```

`LINE_ROLES` 保持不变（不加入 `product_planner`）。

修改 `frontend/src/locales/zh-CN/common.js`：

```js
  roleGroup: {
    system: '系统管理',
    master: '主数据',
    service: '售后角色',
    warehouse: '仓管角色'
  },
```

`role` 增加：

```js
    product_planner: '产品计划',
```

修改 `frontend/src/locales/en-US/common.js`：

```js
  roleGroup: {
    system: 'System',
    master: 'Product master',
    service: 'After-sales',
    warehouse: 'Warehouse'
  },
```

`role` 增加：

```js
    product_planner: 'Product planner',
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```bash
cd frontend && npx vitest run src/utils/roles.spec.js src/views/admin/users/UserList.spec.js --reporter=dot
```
Expected: PASS。

- [ ] **Step 5: 检查点**

不提交，进入 Task 5。

---

## Task 5: 侧栏菜单分组（售后 / 主数据 / 进销存 / 系统）

**Files:**
- Modify: `frontend/src/views/admin/Layout.vue`
- Modify: `frontend/src/views/admin/Layout.spec.js`
- Modify: `frontend/src/locales/zh-CN/admin.js`
- Modify: `frontend/src/locales/en-US/admin.js`

- [ ] **Step 1: 写失败测试**

在 `frontend/src/views/admin/Layout.spec.js` 的 `describe('Layout')` 中新增：

```js
  it('侧栏按售后 / 主数据 / 进销存 / 系统分组，主数据三项连续', async () => {
    const ALL = [
      'ticket:read', 'fault:read', 'stats:read', 'product_line:read',
      'product:read', 'part:read',
      'inventory:sku:read', 'inventory:inbound:read', 'inventory:outbound:read',
      'inventory:movement:read', 'inventory:adjust:write',
      'user:read', 'audit:read'
    ]
    setPermissions(ALL)
    fetchMe.mockResolvedValue({ permissions: ALL })

    const { wrapper } = await mountLayout()
    const groups = wrapper.vm.$.setupState.navGroups

    expect(groups.map((group) => group.label)).toEqual([
      '售后业务',
      '主数据',
      '进销存',
      '系统管理'
    ])
    expect(groups[1].items.map((item) => item.label)).toEqual([
      '产品线',
      '产品管理',
      '零件管理'
    ])
    expect(groups.flatMap((group) => group.items)).toHaveLength(14)
  })
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
cd frontend && npx vitest run src/views/admin/Layout.spec.js --reporter=dot
```
Expected: FAIL — `navGroups` 未定义。

- [ ] **Step 3: 实现分组**

修改 `frontend/src/views/admin/Layout.vue` 模板侧栏：

```html
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item-group
          v-for="group in navGroups"
          :key="group.key"
          :title="group.label"
        >
          <el-menu-item v-for="item in group.items" :key="item.path" :index="item.path">
            {{ item.label }}
          </el-menu-item>
        </el-menu-item-group>
      </el-menu>
```

在 `NAV_ITEMS` 之后增加：

```js
// 菜单分组：产品/零件/产品线从售后作业中独立为「主数据」；
// 分组只是导航层级，权限仍由每一项的 permission 决定。
const NAV_GROUPS = [
  {
    key: 'admin.nav.groupService',
    paths: ['/admin/tickets', '/admin/faults', '/admin/stats']
  },
  {
    key: 'admin.nav.groupMaster',
    paths: ['/admin/product-lines', '/admin/products', '/admin/parts']
  },
  {
    key: 'admin.nav.groupInventory',
    paths: [
      '/admin/inventory/categories',
      '/admin/inventory/skus',
      '/admin/inventory/inbound',
      '/admin/inventory/outbound',
      '/admin/inventory/movements',
      '/admin/inventory/adjustments'
    ]
  },
  {
    key: 'admin.nav.groupSystem',
    paths: ['/admin/users', '/admin/audit-logs']
  }
]

const navGroups = computed(() =>
  NAV_GROUPS.map((group) => ({
    key: group.key,
    label: t(group.key),
    items: group.paths
      .map((path) => navItems.value.find((item) => item.path === path))
      .filter(Boolean)
  })).filter((group) => group.items.length)
)
```

移动端下拉继续使用 `navItems`（扁平），不改 `onNav`。

修改 `frontend/src/locales/zh-CN/admin.js` 的 `nav`：

```js
    groupService: '售后业务',
    groupMaster: '主数据',
    groupInventory: '进销存',
    groupSystem: '系统管理',
```

修改 `frontend/src/locales/en-US/admin.js`：

```js
    groupService: 'After-sales',
    groupMaster: 'Product master',
    groupInventory: 'Inventory',
    groupSystem: 'System',
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```bash
cd frontend && npx vitest run src/views/admin/Layout.spec.js --reporter=dot
```
Expected: PASS。

- [ ] **Step 5: 检查点**

不提交，进入 Task 6。

---

## Task 6: 缺档提示（售后 / 仓管只提示，不新增档案）

**Files:**
- Modify: `frontend/src/views/admin/inventory/SkuList.vue`
- Modify: `frontend/src/views/admin/faults/FaultEdit.vue`
- Modify: `frontend/src/locales/zh-CN/admin-inventory.js`
- Modify: `frontend/src/locales/en-US/admin-inventory.js`
- Modify: `frontend/src/locales/zh-CN/admin-fault.js`
- Modify: `frontend/src/locales/en-US/admin-fault.js`
- Test: `frontend/src/views/admin/inventory/inventoryPages.spec.js`

- [ ] **Step 1: 写失败测试**

在 `frontend/src/views/admin/inventory/inventoryPages.spec.js` 的页面冒烟 describe 中新增：

```js
  it('产品档案为空时提示联系产品计划岗', async () => {
    inv.inventoryRefProducts.mockResolvedValue([])
    wrapper = mount(SkuList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    const create = wrapper.findAll('button').find((b) => b.text().includes('新建 SKU'))
    await create.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('请联系产品/计划岗')
  })
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
cd frontend && npx vitest run src/views/admin/inventory/inventoryPages.spec.js --reporter=dot
```
Expected: FAIL — 提示文案不存在。

- [ ] **Step 3: 实现提示**

修改 `frontend/src/views/admin/inventory/SkuList.vue`：

1. 把 `let partOptionsLoaded = false` 改为：

```js
const partOptionsLoaded = ref(false)
const productLoaded = ref(false)
```

2. `loadProductOptions` 的 `finally` 中加：

```js
  } finally {
    productLoaded.value = true
  }
```

3. `loadPartOptions` 中 `partOptionsLoaded = true` 改为 `partOptionsLoaded.value = true`；`onPartVisibleChange` 改为：

```js
function onPartVisibleChange(visible) {
  if (visible && !partOptionsLoaded.value) loadPartOptions()
}
```

4. 在产品下拉的 `el-form-item` 里、`el-select` 后加：

```html
          <div v-if="productLoaded && !productOptions.length" class="field-hint">
            {{ $t('admin.inventory.sku.productMissingHint') }}
          </div>
```

5. 在零件下拉的 `el-form-item` 里、`el-select` 后加：

```html
          <div v-if="partOptionsLoaded && !partOptions.length" class="field-hint">
            {{ $t('admin.inventory.sku.partMissingHint') }}
          </div>
```

修改 `frontend/src/views/admin/faults/FaultEdit.vue`：

1. 在产品下拉后加：

```html
          <span v-if="canWrite && !products.length && !loadingProducts" class="hint">
            {{ $t('admin.fault.edit.noProductsHint') }}
          </span>
```

2. 现有 `noPartsHint` 的文案改为“联系产品/计划岗”。

修改 `frontend/src/locales/zh-CN/admin-inventory.js` 的 `sku` 段：

```js
    productMissingHint: '暂无产品档案，请联系产品/计划岗建档；也可留空按纯物资处理',
    partMissingHint: '暂无零件档案，请联系产品/计划岗建档；也可留空按纯物资处理',
```

修改 `frontend/src/locales/en-US/admin-inventory.js`：

```js
    productMissingHint: 'No product records yet. Ask the product planner to create one, or leave it blank for general supplies.',
    partMissingHint: 'No part records yet. Ask the product planner to create one, or leave it blank for general supplies.',
```

修改 `frontend/src/locales/zh-CN/admin-fault.js`：

```js
    noProductsHint: '暂无产品档案，请联系产品/计划岗建档',
    noPartsHint: '该产品下还没有零件，请联系产品/计划岗建档',
```

修改 `frontend/src/locales/en-US/admin-fault.js`：

```js
    noProductsHint: 'No product records yet. Ask the product planner to create one.',
    noPartsHint: 'This product has no parts yet. Ask the product planner to create one.',
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```bash
cd frontend && npx vitest run src/views/admin/inventory/inventoryPages.spec.js --reporter=dot
```
Expected: PASS。

- [ ] **Step 5: 检查点**

不提交，进入 Task 7。

---

## Task 7: 文档同步

**Files:**
- Modify: `docs/01-需求设计/进销存模块PRD与数据模型设计.md`
- Modify: `docs/02-技术设计/API接口契约.md`

- [ ] **Step 1: 更新 PRD §1.3 角色表**

在角色表中增加：

```md
| `product_planner` 产品计划 | 维护产品 / 零件 / 产品线主数据；售后与物资只读引用 |
```

把 `supervisor` 行改为“主数据只读；工单 / 故障 / 知识库读写”，把 `warehouse_*` 行改为“产品 / 零件只读引用（`/refs/*`）；库存读写”，把 `super_admin` 行标注“全部权限（break-glass，仅应急）”。

- [ ] **Step 2: 更新 PRD §6.1 / §6.2**

§6.1 增加：

```md
- 新增角色 `product_planner`（产品计划）：`product:read/write`、`part:read/write`、`product_line:read/write`，是主数据唯一常规写者。
- `supervisor` 移除 `product:write` / `part:write` / `product_line:write`，保留三个 `:read`。
- `grantable_permissions()` 排除 `product:write` / `part:write` / `product_line:write`；`super_admin` 仅保留自身 break-glass，不通过临时授权转授主数据写。
- 迁移 008 会收回既有的未过期 `product:write` / `part:write` / `product_line:write` 临时授权，避免历史授权绕过新边界。
```

§6.2 文件表增加：

```md
| `deploy/migrations/008_product_planner.sql` | 角色 CHECK 放宽到 7 角色 |
| `frontend/src/utils/roles.js` 与 `common.js` | 新增 product_planner 与「主数据」角色分组 |
| `frontend/src/views/admin/Layout.vue` | 侧栏分为售后 / 主数据 / 进销存 / 系统四组 |
| `frontend/src/views/admin/inventory/SkuList.vue` / `FaultEdit.vue` | 缺档时提示联系产品/计划岗 |
| `backend/tests/...` / `frontend/...spec.js` | 角色矩阵、grantable、菜单分组、缺档提示基线 |
```

- [ ] **Step 3: 更新 PRD §10.1 与交付关卡**

§10.1 迁移表增加 `008_product_planner.sql`；§12 角色数量从 6 改为 7，grantable 排除项从 3 改为 6。§14 交付关卡增加“产品计划可维护主数据、售后主管写主数据返回 403、仓管仍只读引用”。

- [ ] **Step 4: 更新 API 契约 §0.3**

角色列表改为 7 个（加入 `product_planner`）；在 grantable 端点说明中补充：

```md
> 已排除 `user:write`、`inventory:adjust:write`、`inventory:cost:read`、`product:write`、`part:write`、`product_line:write`。
```

- [ ] **Step 5: 校验文档**

Run:
```bash
.venv/bin/python scripts/dev/check_links.py
.venv/bin/python scripts/dev/check_i18n.py
```
Expected: 0 个无法解析；i18n 通过。

- [ ] **Step 6: 检查点**

不提交，进入 Task 8。

---

## Task 8: 全量验证与部署

- [ ] **Step 1: 后端全量**

Run:
```bash
.venv/bin/python -m pytest backend/tests -q
```
Expected: 全绿；普通模式跳过 2 个 PG 专项用例。

- [ ] **Step 2: PG 迁移幂等**

启动一次性 PostgreSQL（本地已有 `postgres:15-alpine`）：

```bash
docker run -d --rm --name master-review-pg \
  -e POSTGRES_PASSWORD=reviewpass -e POSTGRES_USER=review -e POSTGRES_DB=invtest \
  -p 127.0.0.1:55432:5432 postgres:15-alpine
```

在容器内建一个临时库，执行 `schema.sql` 后连续执行两次 `008`：

```bash
docker exec master-review-pg psql -U review -d invtest -c "CREATE DATABASE migtest"
docker exec -i master-review-pg psql -U review -d migtest -v ON_ERROR_STOP=1 -q < deploy/schema.sql

# 造一条历史 product:write 临时授权，验证 008 会收回它
docker exec master-review-pg psql -U review -d migtest -v ON_ERROR_STOP=1 -q -c "
INSERT INTO users (username, password_hash, real_name, role)
VALUES ('grant_user', 'x', '授权测试', 'supervisor');
INSERT INTO user_permission_grants (user_id, permission, expires_at, reason, granted_by)
SELECT id, 'product:write', NOW() + interval '1 day', '历史授权', id
FROM users WHERE username = 'grant_user';
"

docker exec -i master-review-pg psql -U review -d migtest -v ON_ERROR_STOP=1 -q < deploy/migrations/008_product_planner.sql
docker exec -i master-review-pg psql -U review -d migtest -v ON_ERROR_STOP=1 -q < deploy/migrations/008_product_planner.sql
docker exec master-review-pg psql -U review -d migtest -Atc \
  "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='users_role_check'"
docker exec master-review-pg psql -U review -d migtest -Atc \
  "SELECT count(*) FROM user_permission_grants WHERE permission='product:write' AND revoked_at IS NULL"
```
Expected: 两次执行均成功；约束定义包含 `product_planner`；最后一条计数为 `0`（历史授权已被收回）。

清理：
```bash
docker stop master-review-pg
```

- [ ] **Step 3: 前端全量**

Run:
```bash
cd frontend && npm run lint && npm run test -- --pool=vmThreads --no-file-parallelism && npm run build
```
Expected: lint 0 错误；Vitest 全绿；build 通过。

- [ ] **Step 4: 闸门与 E2E**

Run:
```bash
.venv/bin/python scripts/dev/check_i18n.py
.venv/bin/python scripts/dev/check_links.py
.venv/bin/python scripts/dev/check_duplicate_tests.py
cd frontend && npx playwright test e2e/i18n-layout.spec.js e2e/warehouse-login.spec.js
```
Expected: 三项闸门通过；7 条 E2E 通过。

- [ ] **Step 5: 重建并部署**

Run:
```bash
docker compose -f deploy/docker-compose.yml build backend frontend
docker compose -f deploy/docker-compose.yml --profile migrate run --rm migrate
docker compose -f deploy/docker-compose.yml up -d --no-deps backend frontend
curl -s -o /dev/null -w "HEALTH=%{http_code}\n" http://localhost/health
```
Expected: `migrate` 执行 008（或显示没有待执行迁移）；health 200。

- [ ] **Step 6: 手工验收**

1. 用 `product_planner` 账号登录：能看到产品线/产品/零件页面，且有新增/编辑按钮。
2. 用 `supervisor` 登录：能看到三个主数据页面但无新增/编辑按钮；直接 POST/PUT 产品接口返回 403。
3. 用 `warehouse` 登录：库存菜单正常，看不到主数据菜单；建 SKU 时产品/零件下拉为空显示“请联系产品/计划岗”。
4. 超管在授权面板中看不到 `product:write` / `part:write` / `product_line:write`。

- [ ] **Step 7: 检查点**

不提交，向用户汇报验收结果。

---

## Self-Review

**Spec coverage**
- 新增 product_planner：Task 1、2、4。
- supervisor 去写、页面自动只读：Task 1、2B、4（现有 `hasPermission` 门禁）。
- 主数据写不进临时授权（含历史授权收回）：Task 3、8。
- 主数据菜单分组：Task 5。
- 售后/仓管缺档只提示：Task 6。
- 文档与迁移同步：Task 2、7、8。
- 多角色后续改造：明确不在本计划内，单角色模型保持不变。

**Placeholder scan**
- 无 TBD/TODO；所有代码步骤含实际代码或实际文案。
- 没有“参考 Task N 自行推断”的步骤；关键代码已重复展开。

**Type consistency**
- 角色值统一为 `product_planner`（snake_case），后端 `ROLE_VALUES`、DB CHECK、前端 `ROLE_KEYS` 三处一致。
- 权限码复用 `product:read/write`、`part:read/write`、`product_line:read/write`，未新增权限码。
- 菜单分组 key 与 `admin.nav.groupService/groupMaster/groupInventory/groupSystem` 一致。
- 缺档提示 key 与两套语言包一致。

---

## Execution Handoff

计划已保存到 `docs/superpowers/plans/2026-11-13-product-master-ownership.md`。

推荐 **Subagent-Driven**（你此前偏好子代理执行）：每个 Task 派一个全新子代理，完成后由我按 Task 验收并进入下一个；也可选择 **Inline Execution** 在当前会话按批次执行并设检查点。

回复“按子代理执行”或“当前会话执行”即可开始。
