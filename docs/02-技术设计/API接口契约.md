# API 接口契约

> **版本**：v1.4 ｜ 修订日期：2026-10-22
> **Base URL**：`/api`
> 数据格式：JSON，UTF-8
> 时间格式：ISO 8601 带时区（如 `2026-10-19T10:00:00+08:00`），服务端统一 `TZ=Asia/Shanghai`
> 鉴权：后台接口需 Header `Authorization: Bearer <token>`

## v1.4 修订说明（用户权限、产品线与迁移机制）

| # | 变更 | 原因 |
|---|---|---|
| 1 | 删除"role 不参与鉴权"；改为权限码 + 角色模板 + 数据范围 | 四角色权限已落地，旧说明与实现相反 |
| 2 | 登录响应增加 `permissions`；新增 `GET /api/auth/me` | 前端按权限码渲染菜单、路由与按钮 |
| 3 | 产品 `category` 改为 `line_id` / `line_name`；删除 `category` | 产品线取代分类，且成为数据权限判定依据 |
| 4 | 工单列表/详情/更新增加数据范围与改派规则 | 一线客服只能操作自己产品线工单；改派与认领分离 |
| 5 | 新增用户管理、临时授权、产品线共 13 个端点 | 超管需在界面完成账号与授权维护 |
| 6 | 错误码增加权限、用户、产品线、改派相关 12 项 | 前端需按稳定 code 分支处理 |
| 7 | 部署顺序改为「db 就绪 → 迁移 → 启动后端」 | `/api/health` 只查 `SELECT 1`，旧表结构也可能返回 ok |

## v1.3 修订说明（开发中产品确认）

| # | 变更 | 原因 |
|---|---|---|
| 1 | 工单处理人归属改为「首次处理认领 / 显式转派」，不再"谁改谁拥有" | 原规则下一个客服只改备注就会把工单抢过去，团队协作下归属混乱 |
| 2 | `POST /api/tickets` 增加限流：单 IP 10 次/分钟（burst 3） | 公开写接口可被脚本刷单，污染工单量与积压指标 |

## v1.2 修订说明（第二轮复审后）

| # | 变更 | 原因 |
|---|---|---|
| 1 | 工单号序号改 **4 位**，生成改用 `pg_advisory_xact_lock` | 原 `SELECT MAX(...) FOR UPDATE` 对聚合函数非法；3 位序号在 1000 单后字典序比较失效 |
| 2 | 解决率分母改 `hit=true`，新增 `view_queries` 字段 | 原分母 `fault_id IS NOT NULL` 会因故障删除置 NULL 而缩小，解决率可超 100%；示例数字也算错 |
| 3 | 反馈接口改为幂等（仅状态实际变化才改计数） | 原实现重复点击会重复累加 `resolved_count` |
| 4 | 删除故障/产品/零件时关联记录置 NULL | 原外键为 NO ACTION，契约说置 NULL 但实际会报 FK 错 |
| 5 | 空关键词 `raw_query` 统一写 `null` | 原契约让写"产品名/零件名"，导致 `(未输入关键词)` 这一桶永远为空 |
| 6 | `days=0` 表示"全部" | 原契约最大 365 天，页面"全部"档无法表达 |
| 7 | POST 工单同事务写首条流转日志 | 否则详情历史缺第一行 |
| 8 | `end_date` 改半开区间 | `<= 23:59:59` 会漏掉毫秒级记录 |
| 9 | PUT 工单支持 `need_on_site`，状态变更强制备注 | 录入错误无法更正；页面要求备注必填但接口可绕过 |
| 10 | 补充 `SERVICE_UNAVAILABLE`、`PASSWORD_SAME`；澄清 401 分支 | 原错误码表缺项，且 401 一律跳转会误伤登录失败 |

## v1.1 修订说明

| # | 变更 | 原因 |
|---|---|---|
| 1 | 新增 `GET /api/admin/tickets/{id}` | 原契约只有列表，工单详情抽屉无数据可显示 |
| 2 | `POST /api/tickets`、工单对象增加 `need_on_site` | 原表无此列，上门意愿提交即丢失 |
| 3 | 故障详情返回 `query_log_id`，反馈接口改为必须回传 | 原来无法定位该更新哪条查询日志，并发下串号 |
| 4 | 新增 `POST /api/query-logs` | 一期无自由文本入口，`hit=false` 记录永不产生，未命中看板恒空 |
| 5 | 工单列表增加 `start_date` / `end_date` | PRD F-10 要求时间范围筛选，原契约缺参数 |
| 6 | `top-faults` / `missed` 增加 `days` | 看板时间筛选需对所有区块统一生效 |
| 7 | 工单状态更新从 token 取操作人并写 `ticket_status_logs` | PRD F-10「流转时记录操作人」无字段可落 |
| 8 | 新增 `PUT /api/auth/password` | 验收要求修改默认密码，但没有改密接口 |
| 9 | 统一分页响应结构 `{total, page, page_size, items}` | 原来列表接口未定义响应结构 |
| 10 | 错误体增加 `code` 字段，补业务错误码表 | 型号重复、删除受阻等场景前端只能猜文案 |
| 11 | `GET /api/faults` 增加可选 `q` 关键词参数 | 支撑"未命中检索"闭环 |

---

## 0. 通用约定

### 0.1 分页

所有列表类后台接口统一接受 `page`（默认 1）、`page_size`（默认 20，上限 100），返回：

```json
{
  "total": 56,
  "page": 1,
  "page_size": 20,
  "items": []
}
```

### 0.2 错误响应

```json
{
  "detail": "型号已存在",
  "code": "MODEL_DUPLICATED"
}
```

`code` 为稳定机器码，前端按 `code` 判断分支、按 `detail` 展示文案。完整清单见 §8。

### 0.3 鉴权与授权

> **权限模型**：`users.role` 取值为 `super_admin` / `supervisor` / `agent` / `auditor`，角色对应固定权限码集合；接口按权限码校验（`require("资源:动作")`），不按角色名硬编码。生效权限 = 角色模板权限 ∪ 未过期且未收回的临时授权，并按依赖闭包补齐。数据范围只作用于工单：`ALL` 不受限，`LINES` 仅被授权产品线。

未带 token、token 非法或过期，一律返回：

```json
{ "detail": "登录已过期，请重新登录", "code": "AUTH_TOKEN_EXPIRED" }
```

前端拦截器**只在 `code === "AUTH_TOKEN_EXPIRED"` 时**清除本地 token 并跳转 `/admin/login`。
登录失败同样返回 401，但 `code` 为 `AUTH_INVALID_CREDENTIALS`，必须在表单内提示，**不得触发跳转**（否则用户输错密码会被"闪回"登录页）。

已登录但权限不足（缺少权限码、越权访问工单、无改派权限却传 `assignee_id`）返回 403：

```json
{ "detail": "无权限执行此操作", "code": "PERMISSION_DENIED" }
```

---

## 1. 鉴权

### POST /api/auth/login

**公开**。登录获取 token。

Request:
```json
{ "username": "admin", "password": "Admin@12345" }
```

Response 200:
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_at": "2026-10-21T10:00:00+08:00",
  "user": {
    "id": 1,
    "username": "admin",
    "real_name": "系统管理员",
    "role": "super_admin"
  },
  "permissions": ["fault:read", "fault:write", "product:read", "ticket:read", "..."]
}
```

`permissions` 为**已展开依赖闭包**的生效权限码数组（含未过期且未收回的临时授权），前端直接存入 localStorage，按码渲染菜单/路由/按钮，不再判断角色名。

Error 401：`{"detail": "用户名或密码错误", "code": "AUTH_INVALID_CREDENTIALS"}`
Error 403：`{"detail": "账号已停用", "code": "AUTH_USER_DISABLED"}`

成功后服务端更新 `users.last_login_at`。

---

### GET /api/auth/me

**需鉴权**。返回当前账号与**实时计算**的生效权限，用于跨天/临时授权到期后刷新菜单。

Response 200:
```json
{
  "user": {
    "id": 1,
    "username": "admin",
    "real_name": "系统管理员",
    "role": "super_admin"
  },
  "permissions": ["fault:read", "fault:write", "product:read", "ticket:read", "..."]
}
```

- 401 按 `AUTH_TOKEN_EXPIRED` 处理（清 token 跳登录）；网络错误保持当前页面并提示，不要误退出。
- 前端进入后台布局及每次后台路由切换时调用，角色变更或临时授权到期后菜单及时更新。
- 老版本 localStorage 只有 token、没有 `permissions` 时，路由守卫先调用本接口补齐。

---

### PUT /api/auth/password

**需鉴权**。修改当前登录账号的密码。

Request:
```json
{ "old_password": "Admin@12345", "new_password": "NewPwd@2026" }
```

规则：
- `new_password` 长度 ≥ 8，且不能与旧密码相同（相同返回 400 `PASSWORD_SAME`）
- `confirm_password` 由前端校验（两次一致），不传后端；后端只信任 `new_password`
- 修改成功后**不强制下线**，当前 token 继续有效至过期

Response 200:
```json
{ "success": true, "message": "密码已修改" }
```

Error 400：`{"detail": "原密码不正确", "code": "PASSWORD_INVALID"}`
Error 400：`{"detail": "新密码不能与原密码相同", "code": "PASSWORD_SAME"}`
Error 422：`{"detail": "新密码至少 8 位", "code": "VALIDATION_ERROR"}`

> 本接口任何在用账号都可调用（登录与改密不受权限码限制）。用户管理见 §6；已知限制：改密后不强制下线，超管重置某人密码后其已登录会话仍有效直到 token 过期，停用则下一个请求立即被拒。

---

## 2. 产品

### GET /api/products

**公开**。获取已上架产品列表（`is_active=true`），按 `sort_order` 升序。

Response 200:
```json
[
  {
    "id": 1,
    "name": "智能扫地机器人",
    "model": "X1",
    "line_id": 1,
    "line_name": "扫地机",
    "sort_order": 0
  }
]
```

> 无分页：产品数量在百级以内，一次返全量便于前端缓存。`line_id`/`line_name` 取代原 `category`；客户侧 `ProductPublic` 同样返回这两个字段。

### GET /api/products/{product_id}/parts

**公开**。获取某产品下的零件（级联下拉用），按 `group_name`、`sort_order` 升序。

Response 200:
```json
[
  {
    "id": 1,
    "part_no": "P-X1-001",
    "name": "主刷模组",
    "group_name": "动力系统",
    "sort_order": 1
  }
]
```

Error 404：产品不存在返回 `{"detail": "产品不存在", "code": "NOT_FOUND"}`

### GET /api/admin/products

**需鉴权**。后台产品列表（含已下架）。

Query：`page`、`page_size`、`keyword`（选填，匹配名称或型号）、`is_active`（选填）

Response 200:
```json
{
  "total": 2,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "name": "智能扫地机器人",
      "model": "X1",
      "line_id": 1,
      "line_name": "扫地机",
      "description": "",
      "is_active": true,
      "sort_order": 0,
      "fault_count": 12,
      "created_at": "2026-10-01T09:00:00+08:00",
      "updated_at": "2026-10-01T09:00:00+08:00"
    }
  ]
}
```

> `fault_count` 用于前端在删除前给出提示，避免用户点了删除才被拒。

### POST /api/admin/products

**需鉴权**。

```json
{
  "name": "智能扫地机器人",
  "model": "X1",
  "line_id": 1,
  "description": "",
  "is_active": true,
  "sort_order": 0
}
```

Response 201：返回创建后的产品对象（结构同列表项）。

Error 409：`{"detail": "型号 X1 已存在", "code": "MODEL_DUPLICATED"}`
Error 400：`{"detail": "产品线已停用，不能用于产品", "code": "LINE_INACTIVE"}`
Error 404：`line_id` 不存在

> `line_id` 为必填；`line_name` 由服务端通过关联一次取回（`selectinload`），不接受客户端写入。

### PUT /api/admin/products/{id}

**需鉴权**。Body 同 POST（字段全部可选，传什么改什么）。Response 200：返回更新后的对象。
改型号撞号同样返回 409 `MODEL_DUPLICATED`（不是 500）。

### DELETE /api/admin/products/{id}

**需鉴权**。删除前服务端校验引用：

- 存在零件 → 拒绝
- 存在故障 → 拒绝

历史工单与查询日志中的 `product_id` 不阻止删除，删除后由数据库外键置为 NULL（外键为 `ON DELETE SET NULL`），保留工单内容与统计计数。

Error 409:
```json
{
  "detail": "该产品下还有 3 个零件、12 条故障，请先迁移或删除后再试",
  "code": "DELETE_BLOCKED"
}
```

Response 200：`{"success": true}`

> 数据库层外键为 `ON DELETE RESTRICT`，即使绕过应用层也不会静默级联删除。

---

## 3. 零件

### GET /api/admin/parts

**需鉴权**。Query：`product_id`（必填）、`page`、`page_size`

Response 200:
```json
{
  "total": 3,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "product_id": 1,
      "part_no": "P-X1-001",
      "name": "主刷模组",
      "group_name": "动力系统",
      "sort_order": 1,
      "fault_count": 5
    }
  ]
}
```

### POST /api/admin/parts

**需鉴权**。

```json
{
  "product_id": 1,
  "part_no": "P-X1-001",
  "name": "主刷模组",
  "group_name": "动力系统",
  "sort_order": 1
}
```

Response 201：返回创建后的对象。Error 404：`product_id` 不存在。

### PUT /api/admin/parts/{id}

**需鉴权**。字段可选。Response 200：返回更新后对象。

### DELETE /api/admin/parts/{id}

**需鉴权**。存在关联故障时拒绝，返回 409 `DELETE_BLOCKED`，`detail` 中给出故障条数。

---

## 4. 故障

### GET /api/faults

**公开**。客户侧故障列表。仅返回 `is_published=true`，按 `view_count` 降序。

Query 参数：

| 参数 | 必填 | 说明 |
|---|---|---|
| `product_id` | 是 | 产品 ID |
| `part_id` | 是 | 零件 ID |
| `q` | 否 | 关键词，≤ 50 字符，对 `title`、`symptom` 做不区分大小写的包含匹配 |

Response 200:
```json
[
  {
    "id": 1,
    "title": "开机无反应",
    "symptom": "按开机键后设备完全无响应",
    "view_count": 234
  }
]
```

无结果返回 `[]`（不是 404）。

> **未命中闭环（触发条件以页面行为为准）**
> 前端在客户侧是**本地过滤**（不逐字请求接口），因此上报时机是：
> - 关键词有值且过滤结果为 0 → `POST /api/query-logs`，`raw_query` = 关键词原文（≤50 字）
> - 关键词为空且本接口返回 0 条 → `POST /api/query-logs`，`raw_query` = `null`
> - 同一 `product_id + part_id + raw_query` 30 秒内只上报一次
>
> 直接调用本接口的调用方若拿到空数组，按同一规则自行上报。
> **注意**：空关键词必须写 `null`，不要拼接产品名/零件名 —— 否则看板会把组合名当成"用户搜的词"，"(未输入关键词)"这一桶永远为空。

### GET /api/faults/{id}

**公开**。故障详情。

Query：`q`（选填，透传用户本次检索词，写入日志）

副作用（同一事务内）：
1. `faults.view_count += 1`
2. 插入一条 `query_logs`（`hit=true`，`fault_id` 为本条，`raw_query` 取 `q`）
3. 返回新日志的 `id` 作为 `query_log_id`

Response 200:
```json
{
  "id": 1,
  "product_id": 1,
  "part_id": 1,
  "product_name": "智能扫地机器人",
  "part_name": "电源模组",
  "title": "开机无反应",
  "symptom": "按开机键后设备完全无响应，指示灯不亮",
  "root_cause": "电源适配器损坏 / 电池接触不良",
  "solution_steps": [
    { "step": 1, "text": "检查电源适配器指示灯是否亮起", "image_url": "/uploads/power-led.jpg" },
    { "step": 2, "text": "长按开机键 10 秒强制重启", "image_url": null },
    { "step": 3, "text": "若仍无反应，更换电源适配器测试", "image_url": null }
  ],
  "required_tools": "无",
  "needs_professional": false,
  "attachment_urls": [
    { "name": "维修手册.pdf", "url": "/uploads/manual-x1.pdf", "size": 204800 }
  ],
  "view_count": 235,
  "resolved_count": 180,
  "query_log_id": 8821
}
```

Error 404：故障不存在或未发布，返回 `{"detail": "故障不存在", "code": "NOT_FOUND"}`

> `query_log_id` 是 v1.1 新增字段，前端必须保存，随反馈一起提交。

### POST /api/faults/{id}/feedback

**公开**。用户反馈是否解决。

Request:
```json
{ "query_log_id": 8821, "resolved": true }
```

服务端行为（必须幂等，重复点击、网络重试都不能重复计数）：
1. 校验 `query_log_id` 存在且 `fault_id` 与路径 `{id}` 一致，否则返回 400 `QUERY_LOG_MISMATCH`
2. `UPDATE query_logs SET resolved = :resolved WHERE id = :log_id AND resolved IS DISTINCT FROM :resolved`
3. **仅当第 2 步实际更新了 1 行**时，`resolved=true` 才执行 `faults.resolved_count += 1`；`resolved=false` 则 `-1`（下限 0）
4. 重复提交同一状态视为成功，不改任何计数

Response 200:
```json
{ "success": true, "message": "感谢反馈" }
```

> **不允许**省略 `query_log_id` 的兼容分支：没有它就无法保证并发下更新到正确记录。

### POST /api/query-logs

**公开**。记录一次"检索无结果"。仅用于 `hit=false`，命中场景由详情接口自动写入。

Request:
```json
{
  "product_id": 1,
  "part_id": 1,
  "raw_query": "漏水"
}
```

字段规则：
- `raw_query`：**可为 `null`**（用户没输关键词），最长 100 字符；有值时自动去首尾空格
- `product_id` / `part_id`：必填
- 服务端从请求头补 `ip`、`user_agent`（`user_agent` 截断至 200 字符），不接受客户端传入

Response 201:
```json
{ "id": 8822 }
```

限制：同一 IP 30 次/分钟，另允许 5 次突发（Nginx `rate=30r/m burst=5 nodelay`），超出返回 429 `RATE_LIMITED`。

### GET /api/admin/faults

**需鉴权**。后台故障列表，**不返回 `solution_steps`**（列表不需要，避免大字段拖慢）。

Query：`product_id`、`part_id`（均可选）、`keyword`、`is_published`、`page`、`page_size`

Response 200:
```json
{
  "total": 12,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "product_id": 1,
      "product_name": "智能扫地机器人",
      "part_id": 1,
      "part_name": "电源模组",
      "title": "开机无反应",
      "symptom": "按开机键后设备完全无响应",
      "needs_professional": false,
      "is_published": true,
      "view_count": 234,
      "resolved_count": 180,
      "attachment_count": 1,
      "created_at": "2026-10-01T09:00:00+08:00",
      "updated_at": "2026-10-05T14:00:00+08:00"
    }
  ]
}
```

### GET /api/admin/faults/{id}

**需鉴权**。编辑回显。

字段与公开详情**不同构**，明确如下：
- 业务字段：`product_id`、`part_id`、`title`、`symptom`、`root_cause`、`solution_steps`、`required_tools`、`needs_professional`、`attachment_urls`、`is_published`
- 管理字段：`created_by`、`created_at`、`updated_at`、`view_count`、`resolved_count`
- **不含** `query_log_id`，且**不产生** `view_count` 自增与查询日志（后台编辑回显不是用户访问）

### POST /api/admin/faults

**需鉴权**。

```json
{
  "product_id": 1,
  "part_id": 1,
  "title": "开机无反应",
  "symptom": "按开机键后设备完全无响应",
  "root_cause": "电源适配器损坏",
  "solution_steps": [
    { "step": 1, "text": "检查电源", "image_url": null }
  ],
  "required_tools": "无",
  "needs_professional": false,
  "attachment_urls": [],
  "is_published": true
}
```

校验：`product_id`、`part_id`、`title` 必填；`part_id` 必须属于 `product_id`（否则 400 `PART_PRODUCT_MISMATCH`）；`solution_steps` 元素按 `step` 去重升序。
`created_by` 由服务端从 token 取，前端不传。

Response 201：返回完整对象。

### PUT /api/admin/faults/{id}

**需鉴权**。字段可选，`solution_steps` 整体替换（不是增量合并）。Response 200：返回完整对象。

### DELETE /api/admin/faults/{id}

**需鉴权**。Response 200：`{"success": true}`。
若该故障被工单引用，**不阻止删除**，仅将 `tickets.fault_id` 置为 NULL（数据保留在工单描述里）。

### POST /api/admin/upload

**需鉴权**。文件上传。

Request: `multipart/form-data`，字段名 `file`

限制：
- 后缀白名单 `.jpg .jpeg .png .pdf .mp4`（后端再次校验 MIME，不只看后缀）
- 单文件 ≤ 20MB
- 存储名 `{yyyyMMdd}-{8位随机串}.{ext}`，不保留原文件名

Response 200:
```json
{
  "url": "/uploads/20261019-a1b2c3d4.jpg",
  "filename": "用户上传图片.jpg",
  "size": 102400
}
```

Error 400：`{"detail": "不支持的文件类型", "code": "UPLOAD_TYPE_NOT_ALLOWED"}`
Error 413：`{"detail": "文件超过 20MB 限制", "code": "UPLOAD_TOO_LARGE"}`

> 附件元数据（name/url/size）由前端随故障保存进 `faults.attachment_urls`，服务端不单独建表记录。
>
> **为什么这条要补充说明**：正因服务端不建表，就无法在保存时得知"哪个文件被弃用了"，
> 因此上传文件需要配套的删除与回收机制，见下面 `DELETE /api/admin/upload`
> 与 `deploy/scripts/cleanup-uploads.sh`。

### DELETE /api/admin/upload

**需鉴权**。删除一个未被任何故障引用的上传文件。

前端"移除"图片时调用；不调用则文件永久残留在磁盘。

Query 参数：`url`（上传接口返回的 `url`，如 `/uploads/20261019-a1b2c3d4.jpg`）

校验：
- 文件名必须严格匹配 `save_upload` 生成格式 `{yyyyMMdd}-{8位小写hex}.{ext}`，
  不合格式一律 400（防止删除接口被用作任意文件删除器）
- 文件仍被任一 `faults` 引用时返回 409，**不删除**

Response 200：
```json
{ "success": true }
```

行为约定：
- **幂等**：文件已不存在时同样返回 200，不报 404（多标签页并发移除、清理任务刚跑过都会命中）
- 文件被引用时返回 409，前端应静默忽略——文件留给孤儿清理任务在引用消失后回收

Error 400：`{"detail": "文件名不合法", "code": "VALIDATION_ERROR"}`
Error 409：`{"detail": "该文件仍在故障方案中使用，无法删除", "code": "UPLOAD_IN_USE"}`
Error 503：`{"detail": "服务器暂时无法删除文件，请联系管理员", "code": "SERVICE_UNAVAILABLE"}`

---

## 5. 工单

### POST /api/tickets

**公开**。用户提交工单。

Request:
```json
{
  "product_id": 1,
  "part_id": 1,
  "fault_id": 1,
  "contact": "13800138000",
  "contact_name": "张先生",
  "description": "按步骤试了还是不行，电池刚换过",
  "need_on_site": true
}
```

校验：
- `contact` 必填，长度 5–100（手机号或邮箱）
- `description` 必填，长度 5–2000
- `need_on_site` 必填布尔值
- `product_id` / `part_id` / `fault_id` 选填（用户可能从首页直接进来）

工单号规则：`TK + yyyyMMdd + 4 位当日序号`，如 `TK202610190001`（定长 4 位，保证字典序 = 数值序）。

生成方式（**不要对聚合函数用 FOR UPDATE**，PostgreSQL 不允许）：
```sql
-- 事务内先取按日咨询锁，序列化同日并发
SELECT pg_advisory_xact_lock(hashtext('ticket_no:' || to_char(now(), 'YYYYMMDD')));
-- 再取当日最大序号（定长 4 位，字符串比较安全）
SELECT COALESCE(MAX(right(ticket_no, 4)::int), 0) + 1
FROM tickets WHERE ticket_no LIKE 'TK' || to_char(now(), 'YYYYMMDD') || '%';
```
单日超过 9999 单时直接返回 500 并告警（一期不可能达到），唯一键冲突仍保留 ≤3 次重试作为兜底。
`yyyyMMdd` 取 `Asia/Shanghai` 日期，与 `created_at` 展示日期一致。

Response 201:
```json
{
  "ticket_no": "TK202610190001",
  "created_at": "2026-10-19T10:30:00+08:00"
}
```

同一事务内必须写入首条流转日志，否则详情页的"流转历史"会缺第一行：
`ticket_status_logs(ticket_id, from_status=NULL, to_status='open', operator_id=NULL, remark=NULL)`。

Error 400：`{"detail": "请填写联系方式", "code": "VALIDATION_ERROR"}`

### GET /api/admin/tickets

**需鉴权，权限 `ticket:read`**。工单列表。

> **数据范围**：`super_admin` / `supervisor` / `auditor` 为 `ALL`，不受限；`agent` 为 `LINES`，只返回被授权产品线（`user_product_lines` 未过期）下的工单。过滤发生在搜索之前——`keyword` 只在可见范围内匹配；客服未分配任何产品线时返回 0 条；`tickets.product_id` 为空的工单对客服不可见。

Query：

| 参数 | 必填 | 说明 |
|---|---|---|
| `status` | 否 | `open` / `processing` / `resolved` / `closed`，不传为全部 |
| `start_date` | 否 | 创建时间起（含），`YYYY-MM-DD` |
| `end_date` | 否 | 创建时间止（含当日），`YYYY-MM-DD`。服务端按半开区间处理：`created_at < end_date + INTERVAL '1 day'`，**不要**用 `<= 23:59:59`（会漏掉 23:59:59.001–.999） |
| `keyword` | 否 | 匹配工单号或联系方式 |
| `page` / `page_size` | 否 | 分页 |

Response 200:
```json
{
  "total": 56,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "ticket_no": "TK202610190001",
      "product_name": "智能扫地机器人",
      "product_model": "X1",
      "part_name": "主刷模组",
      "fault_title": "开机无反应",
      "contact": "138****8000",
      "contact_name": "张先生",
      "need_on_site": true,
      "status": "open",
      "assignee_name": null,
      "created_at": "2026-10-19T10:30:00+08:00",
      "updated_at": "2026-10-19T10:30:00+08:00"
    }
  ]
}
```

> 列表中的 `contact` 统一脱敏（保留前 3 位与后 4 位）；完整号码只在详情接口返回。

### GET /api/admin/tickets/{id}

**需鉴权，权限 `ticket:read`**。工单详情（抽屉用）。

> **数据范围**：与列表同一套 `ticket_scope` 校验；客服访问不可见工单返回 403 `PERMISSION_DENIED`，不能只在列表过滤。`tickets.product_id` 为空时仅 `ALL` 范围可见。

Response 200:
```json
{
  "id": 1,
  "ticket_no": "TK202610190001",
  "status": "processing",
  "contact": "13800138000",
  "contact_name": "张先生",
  "need_on_site": true,
  "description": "按步骤试了还是不行，电池刚换过",
  "remark": "已电话联系用户，安排上门",
  "assignee_id": 2,
  "assignee_name": "李工",
  "product": { "id": 1, "name": "智能扫地机器人", "model": "X1" },
  "part": { "id": 1, "name": "主刷模组" },
  "fault": { "id": 1, "title": "开机无反应", "needs_professional": false },
  "created_at": "2026-10-19T10:30:00+08:00",
  "updated_at": "2026-10-19T15:20:00+08:00",
  "history": [
    {
      "from_status": null,
      "to_status": "open",
      "operator_name": null,
      "remark": null,
      "created_at": "2026-10-19T10:30:00+08:00"
    },
    {
      "from_status": "open",
      "to_status": "processing",
      "operator_name": "李工",
      "remark": "已电话联系用户，安排上门",
      "created_at": "2026-10-19T15:20:00+08:00"
    }
  ]
}
```

Error 404：`NOT_FOUND`

### PUT /api/admin/tickets/{id}

**需鉴权，权限 `ticket:write`**。更新状态 / 备注 / 处理人。

Request（字段均可选，至少传一项）：
```json
{
  "status": "processing",
  "remark": "已电话联系用户，安排上门",
  "assignee_id": 2,
  "need_on_site": true
}
```

服务端行为：
1. **数据范围**：更新前同样校验工单可见性，客服改不可见工单返回 403 `PERMISSION_DENIED`
2. `status` 变化时**必须**带非空 `remark`（否则 400 `VALIDATION_ERROR`），并写入 `ticket_status_logs`，`operator_id` 从 token 取（前端不可指定操作人）
3. 处理人归属：
   - 显式传 `assignee_id` → **改派**（转派即确认认领）；操作者必须持有 `ticket:assign`，否则 403 `PERMISSION_DENIED`，**不能靠前端隐藏按钮**
   - 未传且工单**当前无处理人** → 由操作人认领（首次处理即归属）
   - 未传但已有人处理 → **保持原处理人**，不静默抢占；要接手必须显式改派
4. 改派校验：候选人必须启用（否则 400 `ASSIGNEE_DISABLED`）、有 `ticket:write`（否则 400 `ASSIGNEE_NO_PERMISSION`）、对工单产品线可见（否则 400 `ASSIGNEE_OUT_OF_SCOPE`）；`product_id` 为空时只允许 `ALL` 范围账号
5. `remark` 同时更新 `tickets.remark`（只保留最新一条，历史在 logs 里）
6. `need_on_site` 允许更正（客服电话确认后修改）
7. 仅改 `remark` / `need_on_site` 不写流转日志，只更新 `tickets.updated_at`

> 改派到其他产品线后，原处理人不再可见该工单。候选人下拉由 `GET /api/admin/users/assignable` 提供，见 §6。

状态流转约束：

| 当前 | 允许流转到 |
|---|---|
| open | processing、closed |
| processing | resolved、closed |
| resolved | closed（重新打开需新建工单） |
| closed | —（终态） |

Error 400：`{"detail": "不能从 resolved 直接流转到 open", "code": "TICKET_STATUS_INVALID"}`

Response 200：返回更新后的工单详情（结构同 GET 详情）。

---

## 6. 用户管理与产品线

> 本章为 v1.4 新增。除候选人接口外，用户相关端点要求 `user:read` / `user:write`；产品线端点要求 `product_line:read` / `product_line:write`。任何接口都不返回 `password_hash`。

### GET /api/admin/users

**权限 `user:read`**。用户列表。

Query：`keyword`（匹配用户名/姓名，≤100 字）、`role`、`is_active`、`page`、`page_size`

Response 200:
```json
{
  "total": 2,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "username": "admin",
      "real_name": "系统管理员",
      "role": "super_admin",
      "is_active": true,
      "last_login_at": "2026-10-22T09:00:00+08:00",
      "created_at": "2026-10-01T09:00:00+08:00",
      "product_lines": [
        { "id": 1, "name": "扫地机", "expires_at": null }
      ]
    }
  ]
}
```

### GET /api/admin/users/assignable

**权限 `ticket:assign`**。可改派的启用账号，供工单抽屉处理人下拉。

Query：`product_id`（选填；传入时按产品线可见性过滤）

Response 200:
```json
[{ "id": 2, "real_name": "李工" }]
```

候选规则：账号启用、持有 `ticket:write`，且数据范围为 `ALL` 或已被授权该产品线；工单 `product_id` 为空时只返回 `ALL` 范围账号。

### POST /api/admin/users

**权限 `user:write`**。新建账号。

```json
{
  "username": "li",
  "real_name": "李工",
  "password": "Init@12345",
  "role": "agent",
  "product_lines": [
    { "line_id": 1, "expires_at": null },
    { "line_id": 2, "expires_at": "2026-12-31T23:59:59+08:00" }
  ]
}
```

规则：`username` ≤50 且唯一；`real_name` ≤50；密码 8 位以上且 ≤72 字节；`role` 取四个合法值；产品线到期时间必须晚于当前时间或为 `null`（长期）。

Response 201：返回用户列表项结构（同 GET 列表项）。
Error 409：`{"detail": "用户名 li 已存在", "code": "USERNAME_DUPLICATED"}`
Error 404：`line_id` 不存在

### PUT /api/admin/users/{id}

**权限 `user:write`**。修改姓名 / 角色 / 启用状态（用户名不可改）。

```json
{ "real_name": "李工", "role": "supervisor", "is_active": true }
```

硬约束：
- 不能停用自己 → 400 `SELF_DISABLE`
- 不能修改自己的角色 → 400 `SELF_ROLE_CHANGE`
- 停用或降级最后一个在用超管 → 400 `LAST_SUPER_ADMIN`（事务内 `FOR UPDATE` 锁定在用超管行后判断）

不提供删除用户，只停用；历史 `tickets.assignee_id`、`ticket_status_logs.operator_id`、`faults.created_by` 保留。

### POST /api/admin/users/{id}/reset-password

**权限 `user:write`**。服务端生成 12 位密码。

Response 200:
```json
{ "password": "Ab3dEf6hJk9m" }
```

> 明文**只在本次响应返回一次**，不落库、不可再次查看。重置后该用户已登录会话仍有效直到 token 过期（与改密契约一致）；停用则下一个请求立即被拒。

### GET /api/admin/users/{id}/grants

**权限 `user:read`**。临时授权列表，含已过期与已收回记录。

Response 200:
```json
[
  {
    "id": 3,
    "permission": "ticket:assign",
    "expires_at": "2026-11-01T23:59:59+08:00",
    "reason": "双十一临时支援",
    "granted_by_name": "系统管理员",
    "granted_at": "2026-10-22T10:00:00+08:00",
    "revoked_at": null,
    "is_active": true
  }
]
```

### POST /api/admin/users/{id}/grants

**权限 `user:write`**。发放临时授权。

```json
{
  "permission": "ticket:assign",
  "expires_at": "2026-11-01T23:59:59+08:00",
  "reason": "双十一临时支援"
}
```

规则：`expires_at` 必填、必须晚于当前时间、最长 180 天；`reason` 1–200 字。**只增不减**；不可授予 `user:write`；发放者不能授予自己不具备的权限；已停用账号不能发放。

Response 201：返回授权对象（结构同 GET 列表项）。
Error 400：`INVALID_PERMISSION`（不可授予的权限码 / 超出自身权限）、`USER_DISABLED`（目标账号已停用）
Error 422：到期时间或事由不满足校验

### DELETE /api/admin/users/{id}/grants/{grant_id}

**权限 `user:write`**。提前收回。重复收回幂等。

Response 200：`{ "success": true }`
Error 404：`NOT_FOUND`

### PUT /api/admin/users/{id}/product-lines

**权限 `user:write`**。整体替换产品线授权。

```json
[
  { "line_id": 1, "expires_at": null },
  { "line_id": 2, "expires_at": "2026-12-31T23:59:59+08:00" }
]
```

Response 200：返回更新后的用户列表项。传空数组即清空授权（客服随后看到 0 条工单）。

### GET /api/admin/product-lines

**权限 `product_line:read`**。产品线列表。

Query：`is_active`（选填）

Response 200:
```json
{
  "items": [
    {
      "id": 1,
      "name": "扫地机",
      "sort_order": 0,
      "is_active": true,
      "product_count": 8,
      "created_at": "2026-10-22T09:00:00+08:00",
      "updated_at": "2026-10-22T09:00:00+08:00"
    }
  ]
}
```

### POST /api/admin/product-lines

**权限 `product_line:write`**。

```json
{ "name": "净化器", "sort_order": 1 }
```

Response 201：返回产品线对象。Error 409：`LINE_NAME_DUPLICATED`

### PUT /api/admin/product-lines/{id}

**权限 `product_line:write`**。改名、排序、启用/停用。

```json
{ "name": "净化器", "sort_order": 2, "is_active": false }
```

Response 200：返回产品线对象。Error 409：`LINE_NAME_DUPLICATED`

> `is_active=false` 表示不再用于新建产品与新授权；已有产品归属与授权继续有效。

### DELETE /api/admin/product-lines/{id}

**权限 `product_line:write`**。

Response 200：`{ "success": true }`
Error 409：`{"detail": "该产品线下还有 3 个产品，请先迁移后再试", "code": "DELETE_BLOCKED"}`

---

## 7. 统计

> **统一口径（v1.2 明确）**
> - 统计窗口由 `days` 控制：默认 30，`days=0` 表示**全部**（不加时间条件，对应页面"全部"档），其余取值 1–365
> - **自助解决率** = 窗口内 `resolved=true` 的条数 ÷ 窗口内 `hit=true` 的条数 × 100%
>   - 分母用 `hit=true`（查看了方案）而不是 `fault_id IS NOT NULL`：`fault_id` 会因故障被删而置 NULL，但 `hit` 永久保留，否则分母会凭空缩小、解决率虚高甚至超过 100%
> - 不使用 `faults.resolved_count / view_count` 作为看板口径（历史累计值，与时间筛选冲突）
> - `open_tickets` 是**当前积压**，不随窗口变化（见字段说明）

### GET /api/admin/stats/overview

**需鉴权**。Query：`days`（默认 30，`0` 为全部，其余 1–365）

Response 200:
```json
{
  "period_days": 30,
  "total_queries": 1234,
  "view_queries": 1147,
  "resolved_queries": 555,
  "resolve_rate": 0.484,
  "total_tickets": 56,
  "open_tickets": 12,
  "missed_queries": 87
}
```

字段说明：

| 字段 | 口径 |
|---|---|
| `period_days` | 实际统计窗口天数；`days=0`（全部）时返回 `0` |
| `total_queries` | 窗口内 `query_logs` 总条数（= 查看方案数 + 未命中数） |
| `view_queries` | 窗口内 `hit=true` 的条数，**即解决率分母**，页面悬停展示用 |
| `resolved_queries` | 窗口内 `resolved=true` 的条数 |
| `resolve_rate` | `resolved_queries / view_queries`，小数，前端乘 100 显示；分母为 0 时返回 `null` |
| `total_tickets` | 窗口内新建工单数（按 `created_at`） |
| `open_tickets` | **当前** `status IN ('open','processing')` 的数量，**不随窗口变化**（反映当下积压）；页面标注"当前积压"避免与前三张卡混淆 |
| `missed_queries` | 窗口内 `hit=false` 的条数 |

### GET /api/admin/stats/top-faults

**需鉴权**。Query：`days`（默认 30，`0` 为全部）、`limit`（默认 10，上限 50）

排序依据：窗口内 `query_logs.fault_id` 的出现次数（即 `period_views`），不是历史 `view_count` —— 保证与时间筛选一致。

Response 200:
```json
[
  {
    "fault_id": 1,
    "title": "开机无反应",
    "product_name": "智能扫地机器人",
    "part_name": "电源模组",
    "view_count": 234,
    "resolved_count": 180,
    "period_views": 68
  }
]
```

### GET /api/admin/stats/missed

**需鉴权**。Query：`days`（默认 30，`0` 为全部）、`limit`（默认 20，上限 100）

数据来源：窗口内 `hit=false` 的 `query_logs`，按归一化检索词分组计数（去首尾空格 + 转小写），按 `count` 降序。

归一化规则：`COALESCE(NULLIF(lower(btrim(raw_query)), ''), '(未输入关键词)')`
—— 空值统一落进 `(未输入关键词)` 这一行，不与其他关键词混排。

Response 200:
```json
[
  {
    "raw_query": "漏水",
    "count": 23,
    "sample_product_name": "智能扫地机器人",
    "sample_part_name": "水箱模组",
    "last_seen_at": "2026-10-19T18:20:00+08:00"
  }
]
```

> 空 `raw_query` 的记录（用户没输关键词且该组合本身无故障）归入 `raw_query: "(未输入关键词)"` 单独一行，避免与真实关键词混淆。

---

## 8. 错误码表

| HTTP | code | 含义 | 前端处理建议 |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 业务校验失败（参数语义不合法，如空备注改状态） | 高亮对应表单项 |
| 400 | `PASSWORD_INVALID` | 原密码不正确 | 提示重试 |
| 400 | `PASSWORD_SAME` | 新密码与原密码相同 | 提示换一个 |
| 400 | `UPLOAD_TYPE_NOT_ALLOWED` | 文件类型不在白名单 | 提示支持的格式 |
| 400 | `PART_PRODUCT_MISMATCH` | 零件不属于所选产品 | 重置零件选择 |
| 400 | `QUERY_LOG_MISMATCH` | 反馈的日志与故障不匹配 | 静默忽略并刷新详情 |
| 400 | `TICKET_STATUS_INVALID` | 状态流转不被允许 | 刷新列表 |
| 400 | `LAST_SUPER_ADMIN` | 不能停用/降级最后一个在用超级管理员 | 提示至少保留一个在用超管 |
| 400 | `INVALID_PERMISSION` | 临时授权权限码不可授予或超出自身权限 | 刷新可选权限列表 |
| 400 | `SELF_DISABLE` | 不能停用自己 | 提示不能停用当前登录账号 |
| 400 | `SELF_ROLE_CHANGE` | 不能修改自己的角色 | 角色下拉置灰 |
| 400 | `USER_DISABLED` | 目标账号已停用，不能发放临时授权 | 先启用账号 |
| 400 | `ASSIGNEE_DISABLED` | 改派目标账号已停用 | 刷新候选人下拉 |
| 400 | `ASSIGNEE_NO_PERMISSION` | 改派目标没有 `ticket:write` | 刷新候选人下拉 |
| 400 | `ASSIGNEE_OUT_OF_SCOPE` | 改派目标看不到该工单产品线 | 只选同产品线客服或主管 |
| 400 | `LINE_INACTIVE` | 产品线已停用，不能用于产品 | 选择启用中的产品线 |
| 401 | `AUTH_INVALID_CREDENTIALS` | 用户名或密码错误 | 提示，**不跳转** |
| 401 | `AUTH_TOKEN_EXPIRED` | 未登录 / token 过期 | 清 token 跳登录页 |
| 403 | `AUTH_USER_DISABLED` | 账号已停用 | 提示联系管理员 |
| 403 | `PERMISSION_DENIED` | 缺少权限码 / 越权访问工单 / 无改派权限 | 提示无权限；工单场景返回列表并刷新 |
| 404 | `NOT_FOUND` | 资源不存在 | 空态页 |
| 405 | `METHOD_NOT_ALLOWED` | 接口不支持该请求方法（客户端调用错误） | 开发期问题，提示刷新并检查调用方法 |
| 409 | `MODEL_DUPLICATED` | 产品型号重复（POST 与 PUT 均可能） | 表单内联报错 |
| 409 | `USERNAME_DUPLICATED` | 用户名重复 | 用户名输入框内联报错 |
| 409 | `LINE_NAME_DUPLICATED` | 产品线名称重复 | 名称输入框内联报错 |
| 409 | `DELETE_BLOCKED` | 存在关联数据，禁止删除 | 展示 `detail` 中的引用统计 |
| 409 | `UPLOAD_IN_USE` | 上传文件仍被故障方案引用，不可删除 | **静默忽略**（文件留给孤儿清理回收） |
| 413 | `UPLOAD_TOO_LARGE` | 文件超过 20MB | 提示压缩后重试 |
| 422 | `VALIDATION_ERROR` | 字段级校验失败（Pydantic，类型/长度/必填） | 取首条 message 展示 |
| 429 | `RATE_LIMITED` | 触发限流 | 提示稍后再试 |
| 500 | `INTERNAL_ERROR` | 未捕获的服务端异常（全局处理器兜底） | 通用错误提示，不暴露堆栈 |
| 503 | `SERVICE_UNAVAILABLE` | 数据库不可用（health）或上游未就绪（Nginx） | 提示稍后重试 |

## 9. 运维接口

### GET /api/health

**公开**。容器 `healthcheck` 与外部拨测使用。

只检查数据库连通性（`SELECT 1`），不检查业务逻辑，避免业务异常导致容器被反复重启。

Response 200:
```json
{ "status": "ok", "db": "ok" }
```

Error 503:
```json
{ "detail": "数据库不可用", "code": "SERVICE_UNAVAILABLE" }
```

> 该接口必须保持轻量（< 50ms），且不写访问日志。

---

## 10. 端点总览（44 个）

| 分组 | 数量 | 明细 |
|---|---|---|
| 鉴权 | 3 | `POST /auth/login`、`GET /auth/me`、`PUT /auth/password` |
| 公开接口 | 7 | 产品列表、零件级联、故障列表、故障详情、反馈、日志上报、工单提交 |
| 后台内容管理 | 17 | 产品 4 + 零件 4 + 故障 5 + 工单 3 + 上传 1 |
| 用户管理与临时授权 | 9 | 用户列表、候选人、新建、修改、重置密码、授权列表、发放、收回、产品线分配 |
| 产品线 | 4 | 列表、新建、修改、删除 |
| 统计 | 3 | overview / top-faults / missed |
| 运维 | 1 | health |
| **合计** | **44** | 其中需鉴权 **35 个**（内容 17 + 用户 9 + 产品线 4 + 统计 3 + `/auth/me` + 改密） |

> 所有响应保持 `{"detail": string, "code": string}` 结构；`detail` 面向用户可直接展示（中文、无技术细节）。
