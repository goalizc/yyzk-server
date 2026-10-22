# 用户管理、角色权限与产品线数据权限 — 设计稿

- 日期：2026-10-22
- 状态：待评审
- 关联：路线图 3.5（权限与多角色）提前实施；3.1 故障树因依赖二期 AI 对话，不提前

---

## 1. 背景

系统一期已基本可用，但线上运营必须依赖运维脚本（`deploy/scripts/init_admin.py`）加人、停人、重置密码。原计划把用户管理放在三期 3.5，现因上线刚需提前。

一期原裁决见 `docs/05-评估审查/03-评估审查报告.md` C-06：一期不做用户管理，仅保留"修改自己密码"。本次设计推翻该裁决，并把 3.5 中与未来功能无耦合的部分一次做干净：

- 角色定义与操作权限
- 产品线数据权限（工单范围）
- 临时授权

**不提前**：知识库审核流（3.6）、操作日志、客服数据权限扩展到知识库与看板、自定义角色。

## 2. 目标

1. 上线后超管可在界面完成：新建账号、停用/启用、重置密码、改角色、分配产品线。
2. 四类角色登录后，菜单与接口能力符合权限矩阵；越权一律拒绝。
3. 一线客服只能看到、操作自己产品线下的工单。
4. 支持带过期时间的临时授权，到期自动失效。
5. 本次落地后，3.2 多版本、3.6 审核流、四期多租户接入时，**授权层不需要再改结构**。

## 3. 角色定义

`users.role` 取值改为以下四个，代码中集中定义，禁止散落字符串比较：

| 角色 | 代码值 | 职责 | 数据范围 |
|---|---|---|---|
| 超级管理员 | `super_admin` | 账号管理 + 全部业务功能 | `ALL` |
| 售后主管 | `supervisor` | 知识库维护、工单处理、看板 | `ALL` |
| 一线客服 | `agent` | 工单处理、查知识库 | `LINES` |
| 只读审计 | `auditor` | 全部只读 | `ALL` |

迁移：现有 `admin` → `super_admin`，`agent` 保持不变。`role` 为字符串字段，无需改类型。

鉴权实时生效：`get_current_user` 每次请求从数据库读取用户（`backend/app/core/deps.py`），停用、改角色在下一个请求即生效。

## 4. 权限模型

### 4.1 权限码

权限码按 `资源:动作` 命名，集中定义在 `backend/app/core/permissions.py`：

| 权限码 | 覆盖的接口 |
|---|---|
| `ticket:read` | 工单列表、工单详情 |
| `ticket:write` | 工单更新（状态/备注/上门，含首次认领） |
| `ticket:assign` | 工单改派（指定处理人） |
| `product:read` | 产品列表 |
| `product:write` | 产品新建/修改/删除 |
| `part:read` | 零件列表 |
| `part:write` | 零件新建/修改/删除 |
| `fault:read` | 后台故障列表、故障详情 |
| `fault:write` | 故障新建/修改/删除 |
| `upload:write` | 附件上传、删除 |
| `stats:read` | 数据看板三个接口 |
| `user:read` | 用户列表、临时授权列表 |
| `user:write` | 用户新建/修改/停用/重置密码/发临时授权 |
| `product_line:read` | 产品线列表 |
| `product_line:write` | 产品线新建/修改/删除 |

权限码**不建数据库表**，也不做数据库 CHECK 约束。原因：角色是固定四种、权限是代码行为的一部分，放进数据库会带来"改了库没改代码"的漂移；加权限码只改常量 + 矩阵 + 测试，不涉及 DDL。

### 4.2 角色模板

角色 = 权限码集合 + 数据范围，集中在一处：

| 权限 | 超管 | 主管 | 客服 | 审计 |
|---|:---:|:---:|:---:|:---:|
| `ticket:read` | ✅ | ✅ | ✅ | ✅ |
| `ticket:write` | ✅ | ✅ | ✅ | ❌ |
| `ticket:assign` | ✅ | ✅ | ❌ | ❌ |
| `product:read` | ✅ | ✅ | ❌ | ✅ |
| `product:write` | ✅ | ✅ | ❌ | ❌ |
| `part:read` | ✅ | ✅ | ❌ | ✅ |
| `part:write` | ✅ | ✅ | ❌ | ❌ |
| `fault:read` | ✅ | ✅ | ✅ | ✅ |
| `fault:write` | ✅ | ✅ | ❌ | ❌ |
| `upload:write` | ✅ | ✅ | ❌ | ❌ |
| `stats:read` | ✅ | ✅ | ❌ | ✅ |
| `user:read` | ✅ | ❌ | ❌ | ✅ |
| `user:write` | ✅ | ❌ | ❌ | ❌ |
| `product_line:read` | ✅ | ✅ | ❌ | ✅ |
| `product_line:write` | ✅ | ✅ | ❌ | ❌ |

### 4.3 生效权限

```
生效权限 = 角色模板权限 ∪ 未过期且未收回的临时授权
```

- **只增不减**：临时授权不能用来剥夺角色已有权限。
- 临时授权**不可授予 `user:write`**（否则等于可以自我提权）。
- 只有持有 `user:write` 的人（即超管）能发放；发放者不能授予自己不具备的权限。
- `expires_at` 必填、必须晚于当前时间、最长 180 天；`reason` 必填（1–200 字）。
- 到期判定在每次请求时进行，不依赖定时任务；已过期/已收回的记录保留用于追溯。

### 4.4 后端实现

- 新依赖 `require("fault:write")`，放在 `backend/app/core/permissions.py`，返回 403 `PERMISSION_DENIED`。
- 现有接口把 `Depends(get_current_user)` 换成 `Depends(require(...))`，登录与修改自己密码除外（任何在用账号都可调用）。
- `PERMISSION_DENIED` 只登记到 API 契约的错误码表，**不要加入 `_STATUS_CODE_MAP`**：该映射用于没有显式 code 的裸 403（当前映射为 `AUTH_USER_DISABLED`），加入会把停用账号的错误码也改错。`BusinessError` 自带 code，不依赖映射。

### 4.5 临时授权数据模型

```sql
CREATE TABLE user_permission_grants (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission  VARCHAR(30) NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    reason      VARCHAR(200) NOT NULL,
    granted_by  INT REFERENCES users(id) ON DELETE SET NULL,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at  TIMESTAMPTZ
);
CREATE INDEX idx_user_grants_active ON user_permission_grants (user_id, expires_at)
    WHERE revoked_at IS NULL;
```

`permission` 不加数据库 CHECK 约束：新增权限码不应触发 DDL，合法性由应用层常量校验。

### 4.6 权限依赖闭包

部分权限脱离前置权限无法使用。计算生效权限（含临时授权）时按下面的闭包自动补齐，避免"勾了写权限却打不开编辑页"：

| 权限 | 自动补齐 |
|---|---|
| `ticket:write` | `ticket:read` |
| `ticket:assign` | `ticket:read`、`ticket:write` |
| `fault:write` | `fault:read`、`product:read`、`part:read`、`upload:write` |
| `product:write` | `product:read` |
| `part:write` | `part:read`、`product:read` |
| `product_line:write` | `product_line:read` |
| `user:write` | `user:read` |

角色模板本身已满足闭包；闭包用于临时授权的校验与展开，并经 `/auth/me` 下发给前端。前端 `hasPermission` 只看后端展开后的结果，不自行推导依赖。

## 5. 产品线

### 5.1 数据模型

```sql
CREATE TABLE product_lines (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(50) NOT NULL UNIQUE,
    sort_order INT NOT NULL DEFAULT 0,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- products 增加产品线归属，删除 category
ALTER TABLE products ADD COLUMN line_id INT REFERENCES product_lines(id) ON DELETE RESTRICT;
-- 回填后置为 NOT NULL

CREATE TABLE user_product_lines (
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    line_id    INT NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ,           -- NULL = 长期
    PRIMARY KEY (user_id, line_id)
);
```

三个关键取舍：

1. **彻底删除 `products.category`，不做双写兼容**。现有 category（演示数据为"扫地机""净化器"）与"产品线"是同一概念，保留两套必然用错。全仓库引用仅：产品管理页、产品 schema、演示种子、产品测试、public 产品响应。
2. **`line_id` 最终为 NOT NULL**。可空会让数据权限失去判定依据，只能特判。
3. **授权到产品线，不授权到产品型号**。3.2 多版本时 `product_versions` 挂在 `products` 下，产品归属产品线，授权层零改动；3.3 BOM 同理。

`product_lines.is_active=false` 表示不再用于新建产品或新授权；已有归属与授权继续有效。

产品线授权只对数据范围为 `LINES` 的角色（当前仅一线客服）起作用；超管、主管、审计的授权记录可存在但不影响其可见范围。

### 5.2 数据范围只作用于工单

知识库在客户侧完全公开，看板客服无权限，产品/零件管理不涉及客户数据。因此敏感数据只有工单里的联系方式与故障描述，**只给以下三个接口加过滤**：

- `GET /api/admin/tickets`
- `GET /api/admin/tickets/{ticket_id}`
- `PUT /api/admin/tickets/{ticket_id}`

实现：

```
ticket_scope(user):
  scope == ALL   -> 无限制
  scope == LINES -> Ticket.product_id IN (
      SELECT p.id FROM products p
      JOIN user_product_lines upl ON upl.line_id = p.line_id
      WHERE upl.user_id = :uid
        AND (upl.expires_at IS NULL OR upl.expires_at > NOW())
  )
```

边界规则：

1. 客服未分配任何产品线 → 列表返回 0 条，前端提示"尚未分配产品线，请联系管理员"。默认拒绝。
2. `tickets.product_id` 为空的工单 → 仅 `ALL` 范围可见（客服不可见）。
3. **过滤先于搜索**：工单号/联系方式关键字只在可见范围内匹配。
4. 详情与更新同样校验，越权返回 403 `PERMISSION_DENIED`，不能只在列表过滤。
5. 主管、超管、审计不受限；改派规则见 5.3。
6. 产品线授权在用户管理页维护，支持到期时间；临时接手另一条线无需改角色。

### 5.3 工单改派

现有接口接受 `assignee_id`，但前端没有处理人选择器，`apply_update` 只校验"用户存在"。补三处：

1. **新增权限 `ticket:assign`**（超管/主管），改派与认领分离：客服只能首次认领，不能把工单转给别人。`PUT` 工单时只要 payload 含 `assignee_id` 而操作者没有 `ticket:assign`，直接返回 403 `PERMISSION_DENIED`，不能靠前端隐藏按钮。
2. **候选人接口** `GET /api/admin/users/assignable`（权限 `ticket:assign`）：返回启用中、持有 `ticket:write` 的账号 `id/real_name`，供前端下拉。
3. **改派校验**：候选人必须启用且具备 `ticket:write`；若工单 `product_id` 非空，候选人必须对该产品线可见（数据范围 `ALL` 或已被授权该产品线）；`product_id` 为空时只允许选 `ALL` 范围的账号。
4. 未传 `assignee_id` 时保持现有规则：当前无处理人则由操作人认领，已有处理人不抢占。
5. 前端工单抽屉增加处理人下拉，仅 `ticket:assign` 持有者可见；客服没有改派入口，需要转单时由主管操作。把工单改派到其他产品线后，原处理人不再可见。

## 6. 用户管理

### 6.1 接口

除候选人接口外，其余均要求 `user:read` / `user:write`：

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/admin/users` | `user:read` | 列表，支持 keyword（用户名/姓名）、role、is_active、分页 |
| GET | `/api/admin/users/assignable` | `ticket:assign` | 可改派的启用账号（id、real_name），可选 `product_id` 按产品线过滤 |
| POST | `/api/admin/users` | `user:write` | 新建：username、real_name、password、role、product_lines |
| PUT | `/api/admin/users/{id}` | `user:write` | 改 real_name / role / is_active |
| POST | `/api/admin/users/{id}/reset-password` | `user:write` | 服务端生成 12 位密码，响应中返回一次 |
| GET | `/api/admin/users/{id}/grants` | `user:read` | 临时授权列表（含已过期/已收回） |
| POST | `/api/admin/users/{id}/grants` | `user:write` | 发放临时授权：permission、expires_at、reason |
| DELETE | `/api/admin/users/{id}/grants/{grant_id}` | `user:write` | 提前收回 |
| PUT | `/api/admin/users/{id}/product-lines` | `user:write` | 整体替换产品线授权：`[{line_id, expires_at}]` |

产品线接口：

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/admin/product-lines` | `product_line:read` | 列表，支持 `is_active` 过滤 |
| POST | `/api/admin/product-lines` | `product_line:write` | 新建：name、sort_order |
| PUT | `/api/admin/product-lines/{id}` | `product_line:write` | 改名、排序、启用/停用 |
| DELETE | `/api/admin/product-lines/{id}` | `product_line:write` | 仍有产品引用时返回 409 `DELETE_BLOCKED` |

名称重复返回 409 `LINE_NAME_DUPLICATED`。

产品接口变更：

- `POST/PUT /api/admin/products` 的 `category` 字段替换为必填 `line_id`
- 产品列表/详情响应返回 `line_id` 与 `line_name`，不再返回 `category`；列表查询用 `selectinload(Product.line)` 一次取回产品线，避免逐行查询
- 客户侧 `GET /api/products` 同步改为返回 `line_id`、`line_name`（`ProductPublic` 同步调整）

认证侧：

- `POST /api/auth/login` 响应增加 `permissions: string[]`
- 新增 `GET /api/auth/me`，返回 `{ "user": {...}, "permissions": [...] }`，权限为实时计算结果
- `PUT /api/auth/password` 不变

### 6.2 用户字段

列表项：`id, username, real_name, role, is_active, last_login_at, created_at, product_lines[{id, name, expires_at}]`。

**任何接口都不返回 `password_hash`**；重置密码的响应体只有一次性明文密码。

### 6.3 硬约束

1. 不能停用自己。
2. 不能修改自己的角色。
3. 系统内至少保留一个"在用且角色为 super_admin"的账号：停用、降级需校验。
4. 不提供删除用户，只停用（保留 `tickets.assignee_id`、`ticket_status_logs.operator_id`、`faults.created_by` 的历史归属）。
5. 用户名唯一，长度 ≤ 50，密码 ≥ 8 位且 ≤ 72 字节（与现有 bcrypt 限制一致）。
6. 已停用账号的临时授权保留但无效。
7. 最后超管校验在事务内用 `SELECT id FROM users WHERE role='super_admin' AND is_active FOR UPDATE` 锁定在用超管行后再判断，避免两个超管同时互相降级导致无人可用。

### 6.4 已知限制（沿用现有契约）

现有契约规定改密后不强制下线（`backend/app/api/auth.py` 注释）。因此**超管重置某人密码后，该用户已登录的会话仍有效直到 token 过期**；停用则下一个请求立即被拒。本次不改这一行为。

## 7. 前端

### 7.1 权限驱动渲染

- 登录响应与 `/auth/me` 都把 `permissions` 存入 localStorage。
- 菜单、路由、按钮统一按 `hasPermission(code)` 判断，**不再出现角色名判断**；顶栏角色标签映射扩为四个角色值。
- 路由 `meta.permission` 声明所需权限；无权限直接访问 URL 时重定向到有权限的第一个页面。列表页用 `*:read`，编辑页用 `*:write`（如 `/admin/faults/edit/:id?` 要求 `fault:write`）。
- 生效权限按请求实时计算（角色模板 1 次查询 + 临时授权 1 次索引查询），属于读多写少的小表，压测后如成为热点再考虑按请求级缓存。
- 进入后台布局及每次后台路由切换时调用 `/auth/me` 刷新权限（角色变更、临时授权到期后菜单及时更新）。
- **升级兼容**：老版本 localStorage 里只有 token 和 user、没有 permissions。路由守卫生效前若 permissions 缺失，先 `await /auth/me`；请求失败（401/403）则清 token 跳登录，避免"没权限 → 重定向 → 再没权限"的循环。
- `/auth/me` 返回 401 时按 `AUTH_TOKEN_EXPIRED` 处理（清 token 跳登录）；网络错误保持当前页面并提示，不要误退出。

菜单映射：

| 菜单 | 所需权限 |
|---|---|
| 工单管理 | `ticket:read` |
| 产品管理 | `product:read` |
| 零件管理 | `part:read` |
| 故障知识库 | `fault:read` |
| 数据看板 | `stats:read` |
| 用户管理 | `user:read` |

### 7.2 新增页面

| 编号 | 页面 | 路径 | 内容 |
|---|---|---|---|
| P-18 | 用户管理 | `/admin/users` | 列表 + 新建/编辑弹窗 + 重置密码 + 临时授权 |
| P-19 | 产品线管理 | `/admin/product-lines` | 产品线列表与增删改 |

产品管理页的"分类"输入框替换为"产品线"下拉，旁边提供"管理产品线"入口跳转 P-19。P-19 不占侧栏导航项，只能从产品管理页和用户管理页的产品线下拉入口进入；路由权限为 `product_line:read`。

用户管理页交互：

- 新建/编辑：用户名、姓名、角色、初始密码（仅新建）、产品线多选（每项可设到期时间）
- 重置密码：确认后弹窗展示一次性密码 + 复制按钮
- 临时授权：权限码下拉（排除 `user:write`）、到期时间、事由；列表可提前收回
- 编辑自己时，角色与启用状态置灰
- 只读审计进入用户管理页时，隐藏新建/编辑/重置密码/发放授权按钮，只保留列表与授权记录

## 8. 数据库迁移

### 8.1 迁移机制

现状：`deploy/schema.sql` 只在空数据卷由 initdb 执行一次，升级靠手工 DDL（schema.sql 顶部已注明），无法确认各环境是否执行过。本次引入最小机制：

```
schema_migrations (
    version    VARCHAR(50) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

- `deploy/migrations/NNN_name.sql` 按文件名顺序执行
- `deploy/scripts/migrate.py`：读取已应用版本，跳过已完成，逐个在事务中执行并记录；失败即退出。用 Python 而不是 shell + psql，是因为 backend 镜像里没有 psql，但已有 psycopg2
- 新增 compose 一次性服务 `migrate`（与 `init` 同构）：`docker compose run --rm migrate`，挂载 `./scripts` 与 `./migrations`
- `deploy/schema.sql` 表示最新目标状态，并在末尾把随包发布的迁移版本一次性写入 `schema_migrations`（全新库不会重复执行迁移）

### 8.2 本次迁移 `001_user_permissions.sql`

1. 建 `schema_migrations`、`product_lines`、`user_product_lines`、`user_permission_grants`
2. 把 `products.category` 的 `TRIM` 后去重非空值插入 `product_lines.name`；`category` 为空或空串的产品归入"未分类"
3. `products` 增加 `line_id` 并按 category 名称回填，然后 `SET NOT NULL`
4. 删除 `products.category`
5. 删除并重建 `users.role` 的 CHECK 约束，改为 `('super_admin','supervisor','agent','auditor')`；随后执行 `UPDATE users SET role='super_admin' WHERE role='admin'`（顺序不能反，否则旧值违反新约束）
6. 建索引：`user_permission_grants(user_id, expires_at)`、`user_product_lines(line_id)`

迁移是一次性的，不写兼容双读逻辑。

同步修改的代码（不做会直接导致部署失败）：

- `deploy/scripts/init_admin.py`：创建管理员的 SQL 硬编码 `role='admin'`，且 `--role` 的 choices 只有 `agent/admin`。必须改为 `super_admin`，choices 扩为四个角色值；否则全新部署创建的管理员违反新 CHECK，或建出没有任何权限的账号
- `deploy/schema.sql`：users 的 CHECK 改为四个值；products 定义改为 `line_id NOT NULL`、删除 `category`；追加三张新表；末尾写入迁移版本
- `backend/app/core/deps.py` 顶部"role 不参与鉴权"的注释删除
- `backend/app/models/user.py`、`backend/app/models/product.py`：模型字段与注释同步
- `backend/app/api/admin.py` 的 `_PRODUCT_NOT_NULL` 加入 `line_id`
- `backend/app/models/__init__.py`、`backend/app/api/__init__.py`：注册新模型与新路由模块

### 8.3 执行顺序与恢复

**部署顺序必须是：db 就绪 → 迁移 → 启动后端对外服务。**

`deploy.sh` 现在先 `docker compose up -d` 全量起服，再等 `db/backend` healthy。但 `/api/health` 只做 `SELECT 1`（`backend/app/api/health.py`），旧表结构也能返回 ok，于是新代码会在迁移前对外提供 500。改为：

1. `docker compose up -d db`，等 db healthy
2. `docker compose run --rm -T migrate`
3. `docker compose up -d`
4. 等 backend healthy，再初始化管理员

**恢复**：`restore.sh` 是 `DROP SCHEMA` 后整库还原。若还原的是迁移前的备份，库结构停留在旧版本，必须在恢复后追加执行 `docker compose run --rm -T migrate`，否则新代码对旧表。恢复脚本末尾一并做，运维手册记录。

**回滚**：本次迁移删除了 `products.category`，属不可逆变更。执行前必须按现有 `backup.sh` 做一次数据库备份；回滚以备份还原 + 回退镜像为准，不写反向迁移脚本。

## 9. 测试

后端（pytest）：

- 角色 × 接口矩阵：四角色对 15 个权限码对应端点逐一断言 200/403
- 数据范围：客服可见/不可见工单、空产品线、空 product_id、搜索不越界、详情与更新越权
- 改派：候选人必须在用、有 `ticket:write`、对工单产品线可见；空产品工单只能转给 `ALL` 范围
- 临时授权：生效、到期失效、提前收回、不可授予 `user:write`、不可授予超出自身权限、依赖闭包自动补齐
- 用户管理：自停用/自降级被拒、最后一个超管保护、重置密码只返回一次、重复用户名
- 产品线：被产品引用时禁止删除、停用后不可用于新授权
- 迁移：扩展 `scripts/dev/check_orm_pg.py` 校验新表与 ORM 一致

现有测试与联调工具的同步修改（不改会大面积失败）：

| 位置 | 现状 | 改法 |
|---|---|---|
| `backend/tests/conftest.py` | `make_user` 默认 `role="admin"` | 默认 `super_admin`，并提供 `make_user(role=...)` 供矩阵用例 |
| `backend/tests/test_auth.py` | 断言登录返回 `role == "admin"` | 改为 `super_admin` |
| `backend/tests/test_products.py` | 创建/响应含 `category` | 改为 `line_id`，并断言 `line_name` |
| `frontend/src/views/admin/Layout.spec.js` | fixture `role: 'admin'` | 改为 `super_admin`，并注入 permissions |
| `frontend/e2e/*.spec.js` | 用 admin 账号走全流程 | 账号角色迁移后仍可用，补充菜单断言 |
| `scripts/dev/seed_demo.py` | 产品请求带 `category` | 先建产品线，再用 `line_id` |
| `scripts/dev/check_orm_pg.py` | 创建产品时 `category="验证"` | 改为 `line_id` |

前端（vitest）：

- 菜单与路由按 permissions 渲染
- 用户管理页表单校验、重置密码一次性展示、临时授权到期时间
- 产品管理页产品线下拉必填

E2E：四角色登录后菜单项与预期一致；客服访问他人产品线工单 URL 返回 403 页面。

## 10. 验收标准

1. 四角色登录后菜单与接口能力符合第 4.2 节矩阵，越权返回 403 `PERMISSION_DENIED`。
2. 客服只能看到并操作自己产品线下的工单；未分配产品线时看到 0 条并有提示；空产品工单不可见。
3. 超管可在界面完成新建、停用、启用、重置密码、改角色、分配产品线、发放与收回临时授权。
4. 临时授权到期后自动失效，提前收回立即失效。
5. 不能停用自己、不能改自己的角色，系统至少保留一个在用超管。
6. 现有 `admin` 账号迁移后仍可登录且权限完整；现有产品的 category 正确映射为产品线。
7. 超管/主管可维护产品线；删除仍被产品引用的产品线返回 409 `DELETE_BLOCKED`。
8. 主管能把工单改派给同产品线的客服或任意主管；客服无改派入口；候选人下拉不出现无权限或跨线账号。

## 11. 文档同步清单

| 文档 | 修改点 |
|---|---|
| `docs/00-项目管理/项目章程.md` §3 | 用户与权限管理由"三期"改为"一期上线前追加" |
| `docs/01-需求设计/PRD产品需求文档.md` §2/§5 | 四角色定义；删除"一期不提供用户管理界面"；产品线替换产品分类 |
| `docs/01-需求设计/页面清单与交互说明.md` | 新增 P-18、P-19；产品管理页字段变更；菜单按权限渲染 |
| `docs/01-需求设计/用户故事清单.md` | 新增用户管理、产品线授权、临时授权故事 |
| `docs/02-技术设计/API接口契约.md` §0.3/§1/§2/§5/§7 | 删除"role 不参与鉴权"；登录响应加 permissions；新增用户/产品线/临时授权章节；错误码加 `PERMISSION_DENIED`；工单接口数据范围说明 |
| `docs/02-技术设计/系统架构设计.md` | 鉴权层、产品线模型、迁移机制 |
| `docs/完整分期路线图.md` 3.5 | 标注"角色与操作权限已提前落地；数据权限限工单；操作日志仍留在三期" |
| `docs/05-评估审查/01-需求基线清单.md` / `03-评估审查报告.md` | 更新 C-06 裁决与 R-A-15 状态 |
| `docs/00-项目管理/WBS任务拆解.md` / `排期计划.md` | 追加本次任务卡与工期，不改一期历史数据 |
| `docs/03-测试与验收/测试用例清单.md` / `验收检查表.md` | 新增角色矩阵、数据范围、临时授权用例 |
| `docs/04-运维与运营/运维手册.md` | 账号维护从脚本改为界面；脚本保留为应急兜底；新增迁移执行与恢复后迁移说明 |
| 代码注释与测试夹具 | `deps.py`、`user.py`、`product.py` 中"一期不做用户管理/role 不参与鉴权"的注释；conftest、test_auth、test_products、Layout.spec、seed_demo、check_orm_pg |

## 12. 未来扩展点

| 未来功能 | 是否需要改本次结构 |
|---|---|
| 3.2 多版本/批次 | 否。`product_versions` 挂在 products 下，产品归属产品线，授权不变 |
| 3.3 BOM | 否。零件归属产品，产品归属产品线 |
| 3.6 审核流 | 否。新增 `fault:approve` 权限码与角色模板一行；草稿状态是 faults 字段 |
| 操作日志 | 否。新增审计表与埋点，权限模型不动 |
| 四期多租户 | 需加 `tenant_id` 到 users/product_lines，属于四期改造，不影响本期表关系 |
| 自定义角色 | 需把角色模板从代码搬到数据库，本期明确不做 |

## 13. 已定稿的默认决策

以下三项在讨论中按推荐方案定稿，实施中如需变更需先改本稿：

1. 删除 `products.category`，由产品线取代，不做双写兼容。
2. 登录响应与 `/auth/me` 下发权限码，前端按权限码渲染，不再判断角色名。
3. 引入 `schema_migrations` + `deploy/scripts/migrate.py` + `migrate` 一次性服务；部署顺序改为「db 就绪 → 迁移 → 启动后端」。
