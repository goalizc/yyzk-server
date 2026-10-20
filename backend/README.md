# backend

FastAPI 服务。**当前为空，待 S0 任务产出。**

## 计划结构

依据 `docs/02-技术设计/系统架构设计.md` §3：

```
backend/
├── app/
│   ├── main.py              # 应用入口：中间件、异常处理、路由注册
│   ├── config.py            # pydantic-settings 读取环境变量
│   ├── database.py          # engine / SessionLocal / get_db
│   ├── models/              # SQLAlchemy 模型（7 张表）
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── api/                 # health / auth / public / admin / stats
│   ├── services/            # ticket_no / query_log / stats
│   ├── core/                # security / deps / exceptions / logging
│   └── utils/upload.py
├── scripts/init_admin.py    # 由 deploy/scripts 同步或直接引用
├── tests/
├── Dockerfile
└── requirements.txt         # 引用仓库根的 requirements.txt
```

## 本地运行

```bash
cd ..
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend --port 8000
```

## 测试

```bash
.venv/bin/pytest backend/tests -q
```

测试环境用 SQLite（SQLAlchemy 方言切换），PostgreSQL 专属 DDL 只放在 `deploy/schema.sql`，
不在单测里执行。生产/集成验证走 `deploy/docker-compose.yml`。

## 待办（S0）

- [ ] `app/main.py` + `/api/health`
- [ ] `config.py` / `database.py` / 统一异常体 `{detail, code}`
- [ ] `core/security.py`（bcrypt + JWT）+ `POST /api/auth/login` + `PUT /api/auth/password`
- [ ] Dockerfile（python:3.12-slim，非 root 用户，COPY scripts）
