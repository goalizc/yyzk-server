# 售后自助故障诊断系统

面向产品终端用户的自助故障查询 Web 系统：用户按「产品 → 零件 → 故障现象」三级定位，
查看分步图文解决方案；解决不了一键转工单，并带上完整上下文。

目标：把重复性客服工单压下去（上线 3 个月自助解决率 ≥ 30%，高频工单量降 ≥ 40%）。

## 当前状态

| 部分 | 状态 |
|---|---|
| 需求 / 设计 / 测试 / 运维文档 | ✅ v1.2 完成，已过两轮交叉审查 |
| 部署配置（compose / nginx / schema） | ✅ 完成，schema 已在 PostgreSQL 16 上实测通过 |
| 后端代码 | ⬜ 未开始（S0） |
| 前端代码 | ⬜ 未开始（S0） |

一期范围与排除项见 `docs/01-需求设计/PRD产品需求文档.md` §5。

## 目录结构

```
.
├── backend/                  # FastAPI 服务（S0 产出）
├── frontend/                 # Vue 3 + Vite（S0 产出）
├── deploy/                   # 一键部署配置
│   ├── docker-compose.yml     # 4 服务 + 1 个一次性 init
│   ├── schema.sql             # 7 张表建表脚本
│   ├── nginx.conf             # 入口：gzip / 安全头 / 限流 / 错误 JSON 化
│   ├── frontend-nginx.conf    # SPA 路由回退
│   ├── nginx-https.conf.example
│   ├── .env.example
│   ├── data/pg              # 数据库数据（挂载）
│   ├── data/uploads         # 上传文件（挂载，注意属主须为 10001）
│   └── scripts/init_admin.py  # 管理员初始化（幂等）
├── docs/                     # 全部项目文档（索引见 docs/README.md）
├── scripts/dev/              # 开发期工具
│   ├── check_env.sh           # 环境自检
│   ├── pull_images.sh         # 镜像拉取（含镜像站回退）
│   ├── verify_schema.mjs      # 无 PG 环境下校验 schema
│   ├── check_links.py         # 文档内路径引用检查
│   ├── check_duplicate_tests.py  # 测试函数重名检查
│   ├── load_test.py           # 性能压测（TC-70/71）
│   ├── seed_pressure.py       # 压测数据准备
│   ├── seed_demo.py           # 演示知识库写入（无人机机型/零件/故障 + 看板活动数据）
│   ├── demo_data.py           # 演示知识库内容（改机型、补故障只改这里）
│   └── pg_server.mjs          # 无原生 PG 时的 WASM 替代
├── requirements.txt
├── requirements-dev.txt
└── package.json              # 仅供开发工具链使用（非前端工程）
```

## 快速开始

### 生产部署：一条命令

```bash
cd deploy && ./deploy.sh
```

脚本幂等，重复执行安全。它会依次完成：环境检查 → 生成 `.env` 并随机化密钥 →
建数据目录 → 构建镜像 → 修正上传目录属主 → 起服务等 healthy → 初始化管理员 →
健康验证 → 注册每日清理 → 打印访问地址。

**不要用 `sudo`**——需要 root 的唯一动作已在容器内完成。

```bash
./deploy.sh --check      # 体检：只查不改
./deploy.sh --rebuild    # 改了代码后强制重建
./deploy.sh --skip-cron  # 不注册定时清理
```

详细说明与手动部署兜底流程见 `docs/04-运维与运营/运维手册.md`。

### 本地开发

```bash
# 环境自检（docker / compose / 端口）
bash scripts/dev/check_env.sh --pull

# 起数据库（首次自动执行 schema.sql）
cd deploy && cp -n .env.example .env
mkdir -p data/pg data/uploads
docker compose up -d db
```

后端热重载（不打包容器）：

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend --port 8000
```

详见 `docs/开发环境搭建.md`。

## 常用命令

| 目的 | 命令 |
|---|---|
| 一键部署 | `cd deploy && ./deploy.sh` |
| 部署体检 | `cd deploy && ./deploy.sh --check` |
| 环境自检 | `bash scripts/dev/check_env.sh --pull` |
| 拉基础镜像 | `bash scripts/dev/pull_images.sh` |
| 校验建表脚本 | `node scripts/dev/verify_schema.mjs` |
| 校验文档链接 | `python scripts/dev/check_links.py` |
| 检查测试重名 | `python scripts/dev/check_duplicate_tests.py` |
| 后端测试 | `.venv/bin/pytest -q` |
| 写入演示数据（幂等） | `.venv/bin/python scripts/dev/seed_demo.py --via-sql --activity` |
| 重置演示数据（换机型） | `.venv/bin/python scripts/dev/seed_demo.py --reset --via-sql --activity` |
| 前端构建 | `cd frontend && npm run build` |
| 清理上传残留 | `cd deploy && ./scripts/cleanup-uploads.sh`（预演，加 `--apply` 执行） |
| 清理过期审计 | `cd deploy && ./scripts/cleanup-audit.sh`（默认保留 180 天，加 `--apply` 执行） |

## 文档入口

先看这两份，再按需翻其他：

- `docs/README.md` —— 文档总索引
- `docs/05-评估审查/04-修复记录.md` —— 改过什么、为什么改、还剩什么

## 约定

- **路径一律以仓库根为基准**写（如 `docs/02-技术设计/API接口契约.md`、`deploy/schema.sql`）
- 分支：`main` 受保护，开发在 `feat/*`，修复在 `fix/*`
- 提交：`<type>: <subject>`，type ∈ feat / fix / docs / chore / test / refactor
- 密钥只放 `deploy/.env`（已 gitignore），仓库内只留 `.env.example`

## 技术栈

后端 FastAPI + SQLAlchemy 2.0 + PostgreSQL 15；前端 Vue 3 + Vite + Element Plus；
Nginx 同源反代；Docker Compose 编排；单机 4 核 8G 可跑，全私有化部署。
