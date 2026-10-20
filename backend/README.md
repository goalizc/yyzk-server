# backend

FastAPI 服务。**后端已完成契约里的全部 30 个端点**：鉴权 2、公开 7、后台内容管理 17、统计 3、运维 1。
接下来是前端页面（C 阶段）。

## 已实现

| 能力 | 位置 | 说明 |
|---|---|---|
| `GET /api/health` | `app/api/health.py` | 只查 DB 连通性，失败返回 503 `SERVICE_UNAVAILABLE`，供容器 healthcheck |
| `POST /api/auth/login` | `app/api/auth.py` | 返回 token + `expires_at`（带 `+08:00`），更新 `last_login_at` |
| `PUT /api/auth/password` | `app/api/auth.py` | 校验原密码、拒绝新旧相同、新密码 ≥ 8 位 |
| `GET /api/products` | `app/api/public.py` | 公开产品列表，仅 `is_active=true`，按 `sort_order` 升序，无分页 |
| `GET /api/products/{id}/parts` | `app/api/public.py` | 级联下拉用，按 `group_name`、`sort_order` 升序；产品不存在返回 404 |
| `/api/admin/products` CRUD | `app/api/admin.py` | 列表分页 + `keyword`/`is_active` 过滤 + `fault_count`；型号重复 409 `MODEL_DUPLICATED` |
| `/api/admin/parts` CRUD | `app/api/admin.py` | 列表按 `product_id` 必填过滤 + `fault_count`；有故障引用时删除返回 409 `DELETE_BLOCKED` |
| `GET /api/faults` | `app/api/public.py` | 仅已发布，按 `view_count` 降序；`q` 匹配标题与现象 |
| `GET /api/faults/{id}` | `app/api/public.py` | 副作用：`view_count` 原子 +1、写 `query_logs(hit=true)`、返回 `query_log_id` |
| `POST /api/faults/{id}/feedback` | `app/api/public.py` | 幂等：仅状态变化时增减 `resolved_count`，错配 400 `QUERY_LOG_MISMATCH` |
| `POST /api/query-logs` | `app/api/public.py` | 记录未命中；服务端补 ip/UA（UA 截断 200），零件归属错配 400 |
| `/api/admin/faults` CRUD | `app/api/admin_faults.py` | 列表不含 `solution_steps`；回显不写日志、不自增浏览数；`created_by` 取自 token |
| `POST /api/admin/upload` | `app/api/admin.py` | 后缀白名单 + 文件头签名双校验；**流式落盘**，≥20MB 返回 413 |
| `POST /api/tickets` | `app/api/public.py` | 公开提交，工单号 `TK+日期+4 位`（咨询锁串行），同事务写首条流转日志 |
| `/api/admin/tickets` | `app/api/admin_tickets.py` | 列表（联系方式脱敏、状态/日期/关键词过滤）、详情（完整号码+流转历史）、状态流转校验；处理人：首次处理认领，转派需显式指定 |
| `/api/admin/stats/*` | `app/api/stats.py` | overview / top-faults / missed；口径在 `backend/app/services/stats.py`，解决率分母用 `hit=true` |
| 统一错误体 | `app/core/exceptions.py` | `{"detail": 中文, "code": 机器码}`，堆栈只进日志 |
| 结构化日志 | `app/core/logging.py` | 单行 JSON 到 stdout，含 `request_id / method / path / status / duration_ms` |
| 日志写入 | `app/services/query_log.py` | 客户端 ip/UA 提取与日志构造，与业务同事务 |
| 分页助手 | `app/services/pagination.py` | 统一 `{total, page, page_size, items}`，`page_size` 上限 100 |
| 7 张表模型 | `app/models/` | 与 `deploy/schema.sql` 一一对应（DDL 以 schema.sql 为准） |

错误码严格按 `docs/02-技术设计/API接口契约.md` §7，不新增未登记的码。
时间字段统一输出 `+08:00`（`app/core/time.py`，兼容 SQLite 的 naive datetime）。

## 目录

```
backend/
├── app/
│   ├── main.py          # 应用入口：中间件、异常处理、路由
│   ├── config.py        # pydantic-settings，缺 JWT_SECRET/DATABASE_URL 启动即失败
│   ├── database.py      # 连接池 pool_size=5 / max_overflow=10
│   ├── models/          # users products parts faults query_logs tickets ticket_status_logs
│   ├── schemas/         # auth / product / part / common
│   ├── api/             # health / auth / public / admin / admin_faults / admin_tickets / stats
│   ├── services/        # pagination / query_log / ticket / ticket_no / stats
│   ├── utils/           # upload（流式+文件头校验）、search（LIKE 转义）
│   └── core/            # security / deps / exceptions / logging / time
├── tests/               # pytest + SQLite
└── Dockerfile
```

## 本地运行

```bash
# 仓库根目录
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# 方式一：连 compose 里的 db（推荐）
cd deploy && docker compose up -d db && cd ..
DATABASE_URL="postgresql+psycopg2://fault:<密码>@localhost:5432/fault_db" \
JWT_SECRET="$(openssl rand -hex 32)" \
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000

# 方式二：只跑接口逻辑，用 SQLite
DATABASE_URL="sqlite:///./.tmp/dev.db" JWT_SECRET="$(openssl rand -hex 32)" \
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000

# 方式三：既没有 PostgreSQL 也没有 Docker —— 起一个 WASM PostgreSQL（真 pg 协议）
npm run dev:pg                     # 仓库根执行，监听 55432，首次自动建表
DATABASE_URL="postgresql+psycopg2://postgres@127.0.0.1:55432/postgres" \
JWT_SECRET="$(openssl rand -hex 32)" \
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000
# 管理员账号仍需初始化：
# cd deploy && DATABASE_URL=... ADMIN_INIT_PASSWORD='至少8位' python ../scripts/init_admin.py
```

接口文档：默认**关闭**（不对外暴露接口清单）。本地要看加 `DEBUG=true`：

```bash
DEBUG=true .venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000
# → http://localhost:8000/api/docs（经 Nginx 后为 /api/docs）
```

## 测试

```bash
.venv/bin/pytest              # 在仓库根目录执行，读 pytest.ini
```

单测用 SQLite 内存库，只验证接口行为与错误码；PostgreSQL 专属 DDL 不在此执行，
建表由 `deploy/schema.sql` 负责。

## 镜像说明

- 构建上下文是**仓库根目录**（compose 里 `context: ..`），
  这样 `requirements.txt`、`deploy/scripts/init_admin.py` 只有一份。
- 容器以非 root `uid=10001` 运行；宿主机挂载的 `deploy/data/uploads`
  需 `sudo chown -R 10001:10001 deploy/data/uploads`，否则上传会因权限失败。
  同理，上传的文件在宿主机上属 `uid=10001`，清理/迁移要用 `sudo` 或
  `docker exec fault-backend rm /data/uploads/<name>`。
- `uvicorn --workers 2`，访问日志由应用中间件统一输出（已关掉 uvicorn 自带那条）。
- 构建源走 build args（默认清华 pip + npmmirror），可用 `deploy/.env` 覆盖；
  卡住时用 `bash scripts/dev/build.sh backend` 看是哪一步停住。

## 待办

- [ ] 前端页面（C-02 起）：客户侧三级级联、方案详情、工单提交、后台各页面与看板
- [ ] 限流补强（待确认）：`/api/faults/{id}` 加 Nginx `limit_req`（`/api/tickets` 已加，10r/m burst 3）
- [ ] 反馈防刷（契约变更待确认）：`query_log_id` 加时效或 IP 绑定，避免猜 id 刷解决率
