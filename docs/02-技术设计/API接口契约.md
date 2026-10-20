# API 接口契约

> **版本**：v1.2 ｜ 修订日期：2026-10-20
> **Base URL**：`/api`
> 数据格式：JSON，UTF-8
> 时间格式：ISO 8601 带时区（如 `2026-10-19T10:00:00+08:00`），服务端统一 `TZ=Asia/Shanghai`
> 鉴权：后台接口需 Header `Authorization: Bearer <token>`

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

`code` 为稳定机器码，前端按 `code` 判断分支、按 `detail` 展示文案。完整清单见 §7。

### 0.3 鉴权失败

> **角色说明**：`users.role` 有 `admin` / `agent` 两个值，但**一期不参与鉴权判断** —— 两者可调用的接口完全相同（PRD §5 已声明不做权限管理）。不要按 role 额外加限制，否则与文档不一致。

未带 token、token 非法或过期，一律返回：

```json
{ "detail": "登录已过期，请重新登录", "code": "AUTH_TOKEN_EXPIRED" }
```

前端拦截器**只在 `code === "AUTH_TOKEN_EXPIRED"` 时**清除本地 token 并跳转 `/admin/login`。
登录失败同样返回 401，但 `code` 为 `AUTH_INVALID_CREDENTIALS`，必须在表单内提示，**不得触发跳转**（否则用户输错密码会被"闪回"登录页）。

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
    "role": "admin"
  }
}
```

Error 401：`{"detail": "用户名或密码错误", "code": "AUTH_INVALID_CREDENTIALS"}`
Error 403：`{"detail": "账号已停用", "code": "AUTH_USER_DISABLED"}`

成功后服务端更新 `users.last_login_at`。

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

> 一期不做用户增删改与角色权限管理（见 PRD §5 边界）。本接口只解决"必须能改默认密码"这一验收项。

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
    "category": "扫地机",
    "sort_order": 0
  }
]
```

> 无分页：产品数量在百级以内，一次返全量便于前端缓存。

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
      "category": "扫地机",
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
  "category": "扫地机",
  "description": "",
  "is_active": true,
  "sort_order": 0
}
```

Response 201：返回创建后的产品对象（结构同列表项）。

Error 409：`{"detail": "型号 X1 已存在", "code": "MODEL_DUPLICATED"}`

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

**需鉴权**。工单列表。

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

**需鉴权**。工单详情（抽屉用）。

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

**需鉴权**。更新状态 / 备注 / 处理人。

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
1. `status` 变化时**必须**带非空 `remark`（否则 400 `VALIDATION_ERROR`），并写入 `ticket_status_logs`，`operator_id` 从 token 取（前端不可指定操作人）
2. `assignee_id` 不传时默认设为当前登录用户
3. `remark` 同时更新 `tickets.remark`（只保留最新一条，历史在 logs 里）
4. `need_on_site` 允许更正（客服电话确认后修改）
5. 仅改 `remark` / `need_on_site` 不写流转日志，只更新 `tickets.updated_at`

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

## 6. 统计

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

## 7. 错误码表

| HTTP | code | 含义 | 前端处理建议 |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | 业务校验失败（参数语义不合法，如空备注改状态） | 高亮对应表单项 |
| 400 | `PASSWORD_INVALID` | 原密码不正确 | 提示重试 |
| 400 | `PASSWORD_SAME` | 新密码与原密码相同 | 提示换一个 |
| 400 | `UPLOAD_TYPE_NOT_ALLOWED` | 文件类型不在白名单 | 提示支持的格式 |
| 400 | `PART_PRODUCT_MISMATCH` | 零件不属于所选产品 | 重置零件选择 |
| 400 | `QUERY_LOG_MISMATCH` | 反馈的日志与故障不匹配 | 静默忽略并刷新详情 |
| 400 | `TICKET_STATUS_INVALID` | 状态流转不被允许 | 刷新列表 |
| 401 | `AUTH_INVALID_CREDENTIALS` | 用户名或密码错误 | 提示，**不跳转** |
| 401 | `AUTH_TOKEN_EXPIRED` | 未登录 / token 过期 | 清 token 跳登录页 |
| 403 | `AUTH_USER_DISABLED` | 账号已停用 | 提示联系管理员 |
| 404 | `NOT_FOUND` | 资源不存在 | 空态页 |
| 409 | `MODEL_DUPLICATED` | 产品型号重复（POST 与 PUT 均可能） | 表单内联报错 |
| 409 | `DELETE_BLOCKED` | 存在关联数据，禁止删除 | 展示 `detail` 中的引用统计 |
| 413 | `UPLOAD_TOO_LARGE` | 文件超过 20MB | 提示压缩后重试 |
| 422 | `VALIDATION_ERROR` | 字段级校验失败（Pydantic，类型/长度/必填） | 取首条 message 展示 |
| 429 | `RATE_LIMITED` | 触发限流 | 提示稍后再试 |
| 500 | `INTERNAL_ERROR` | 未捕获的服务端异常（全局处理器兜底） | 通用错误提示，不暴露堆栈 |
| 503 | `SERVICE_UNAVAILABLE` | 数据库不可用（health）或上游未就绪（Nginx） | 提示稍后重试 |

## 8. 运维接口

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

## 9. 端点总览（30 个）

| 分组 | 数量 | 明细 |
|---|---|---|
| 鉴权 | 2 | `POST /auth/login`、`PUT /auth/password` |
| 公开接口 | 7 | 产品列表、零件级联、故障列表、故障详情、反馈、日志上报、工单提交 |
| 后台内容管理 | 17 | 产品 4 + 零件 4 + 故障 5 + 工单 3 + 上传 1 |
| 统计 | 3 | overview / top-faults / missed |
| 运维 | 1 | health |
| **合计** | **30** | 其中需鉴权 **21 个**（后台 17 + 统计 3 + 改密 1） |

> 所有响应保持 `{"detail": string, "code": string}` 结构；`detail` 面向用户可直接展示（中文、无技术细节）。
