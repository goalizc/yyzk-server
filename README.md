# 售后自助故障诊断系统

面向产品终端用户的自助故障查询 Web 系统：用户先选**产品和零件**，再从故障现象列表里
找到与自己情况一致的一条，查看分步图文解决方案；解决不了一键转工单，并带上完整上下文。

目标：把重复性客服工单压下去（上线 3 个月自助解决率 ≥ 30%，高频工单量降 ≥ 40%）。

## 当前状态

| 部分 | 状态 |
|---|---|
| 后端 | ✅ 完成：客户查询 / 工单 / 知识库 / 产品与零件 / 用户与授权 / 审计 / 统计 / 进销存，21 张业务表、75 个 API 操作、27 个权限码 |
| 前端 | ✅ 完成：客户侧 4 页 + 后台 14 页，中英双语 |
| 部署 | ✅ 一键脚本 + Compose（backend / frontend / nginx / db），单机 4C8G 已跑通 |
| 文档 | ✅ 需求、设计、测试、运维、评估审查齐备（索引见 `docs/README.md`） |
| 验收 | ✅ 运维 / 安全 / 性能 / 移动端四条路线已过，真机 iOS Safari 待补 |

一期范围与排除项见 `docs/01-需求设计/PRD产品需求文档.md` §5。

## 质量基线

| 项 | 命令 | 当前 |
|---|---|---|
| 后端测试 | `.venv/bin/python -m pytest backend/tests -q` | 391 passed / 2 skipped |
| 前端单测 | `cd frontend && npm run test` | 285 passed / 32 文件 |
| 前端 E2E | `cd frontend && npm run e2e` | 12 条冒烟全过 |
| 前端 lint | `cd frontend && npm run lint` | 无告警 |
| 国际化闸门 | `python scripts/dev/check_i18n.py` | 无硬编码中文 |
| Schema 闸门 | `node scripts/dev/verify_schema.mjs` | 12/12（含表集合、7 角色双向断言） |
| 文档链接 | `python scripts/dev/check_links.py` | 639 引用 0 失败 |

> 上面这几个数字会过期，改测试后请顺手更新；命令本身才是基线。
> `pytest` 的汇总行被 `pytest.ini` 的 `addopts` 吃掉时，加 `-o addopts=""` 才看得到
> 「N passed」——`-q` 的进度点看着全绿也可能藏着 skip。

E2E 依赖已启动的全栈（`cd deploy && ./deploy.sh`），跑的是真实浏览器 + 真实后端。
冒烟用例里 `warehouse-login.spec.js` 需要一个「纯仓管」账号，首次跑之前执行一次
`cd deploy && ./scripts/ensure-e2e-user.sh`（幂等；测试栈加
`STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test`）。

## 主要能力

- **客户侧**：产品/零件两级选择 → 故障现象列表（标题 + 现象 + 浏览量，关键词即时过滤，
  5 条折叠，空结果可直接提交工单）→ 方案详情（分步图文 + 附件）→ 反馈 / 转工单
- **后台**：工单流转（状态、备注、改派）、故障知识库（步骤与图片）、数据看板、
  产品线 / 产品 / 零件维护、用户与临时授权、操作审计
- **国际化**：中英双语。客户侧语言由 URL 前缀决定（`/en/...`，可直接分享），
  后台按本机偏好记忆；Element Plus 内置文案随语言切换
- **安全**：JWT 24 小时 + **空闲 60 分钟自动登出**（隔夜开机不再保持登录）；
  密码 bcrypt；审计日志 append-only 保留 190 天；上传后缀白名单 + 重命名存储

## 目录结构

```
.
├── backend/                      # FastAPI 服务
│   ├── app/
│   │   ├── api/                  # 路由：public / admin_* / auth / stats / health
│   │   ├── core/                 # 配置、安全、鉴权、权限码、异常
│   │   ├── models/ schemas/      # ORM 与 Pydantic 模型
│   │   └── services/             # 业务逻辑（工单号、审计、上传回收等）
│   └── tests/                    # pytest
├── frontend/                     # Vue 3 + Vite + Element Plus
│   ├── src/
│   │   ├── views/public/         # 客户侧 4 页
│   │   ├── views/admin/          # 后台 14 页（按模块分目录）
│   │   ├── components/           # DetailPanel / LangSwitch / FaultSolutionView …
│   │   ├── router/ locales/ utils/ api/
│   │   └── …                     # 单测与被测文件同目录（*.spec.js）
│   └── e2e/                      # Playwright（smoke / walkthrough / mobile）
├── deploy/                       # 一键部署
│   ├── docker-compose.yml        # 4 服务 + 一次性 init
│   ├── schema.sql                # 21 张业务表（+ schema_migrations）
│   ├── migrations/               # 增量 SQL（001~009，含审计防篡改触发器）
│   ├── nginx*.conf               # 入口：gzip / 安全头 / 限流 / 错误 JSON 化
│   ├── scripts/                  # init_admin / prepare-storage / cleanup-* / install-cron
│   └── data/                     # pg 与 uploads 挂载（注意 uploads 属主须为 10001）
├── docs/                         # 全部项目文档（索引见 docs/README.md）
├── scripts/dev/                  # 开发期工具（见下方「常用命令」）
└── requirements*.txt  package.json  pytest.ini
```

## 快速开始

### 生产部署：一条命令

```bash
cd deploy && ./deploy.sh
```

脚本幂等，重复执行安全。依次完成：环境检查 → 生成 `.env` 并随机化密钥 → 建数据目录 →
构建镜像 → 修正上传目录属主 → 起服务等 healthy → 初始化管理员 → 健康验证 → 注册每日清理 →
打印访问地址。

**不要用 `sudo`** —— 需要 root 的唯一动作已在容器内完成。管理员账号见 `deploy/.env`
的 `ADMIN_USERNAME`，初始密码由脚本生成并打印（仓库内不留明文）。忘记密码时：

```bash
cd deploy && docker compose exec backend \
  python /app/scripts/init_admin.py user passwd admin --password '<新密码>'
```

重置会顺带作废该账号已登录的会话（`token_version` +1）。

```bash
./deploy.sh --check      # 体检：只查不改
./deploy.sh --rebuild    # 改了代码后强制重建
./deploy.sh --skip-cron  # 不注册定时清理
```

**改了前端代码必须重建镜像**（产物构建进镜像，`up -d` 不感知源码变化）：

```bash
cd deploy && docker compose build frontend && docker compose up -d frontend
```

详细说明与手动部署兜底流程见 `docs/04-运维与运营/运维手册.md`。

### 测试栈：与生产同机，8080

生产继续占用 80；测试栈使用独立数据库、上传目录和 JWT 密钥，互不影响：

```bash
cd deploy
cp -n .env.test.example .env.test
# 修改 .env.test 里的数据库密码、JWT_SECRET、ADMIN_INIT_PASSWORD
./deploy-test.sh
```

- 访问：`http://127.0.0.1:8080/`（默认只监听本机；需要局域网访问时把 `.env.test` 的 `HTTP_BIND` 改成 `0.0.0.0`——但 `DEBUG=true` 会把 `/api/docs` 一并暴露，务必加防火墙或带鉴权的反代）
- 数据目录：`deploy/data-test/`
- 环境变量：`deploy/.env.test`（已 gitignore，模板见 `deploy/.env.test.example`）。模板里的 `CHANGEME_*` 必须全部改掉，否则 `deploy-test.sh` 会拒绝启动
- 容器：`fault-test-db/backend/frontend/nginx`，镜像也是独立的 `fault-test-*`（不会覆盖生产镜像，但会多占一份磁盘）
- 停止：`cd deploy && docker compose -p fault-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml down`（数据保留）

测试栈首次启动会建空库并初始化管理员：`deploy-test.sh` 会自动执行 migrate + init。

**两栈共享的面**：`docker-compose.yml`、`nginx.conf` 和前后端代码。改这三处后两栈都要重建才生效；`deploy/scripts/enable-https.sh` 改的正是共享的 compose/nginx 文件，但**只重建当前目标栈的 nginx**——两栈都要 HTTPS 就各跑一次（先生产、后测试，避免两个栈抢宿主机 443）。

**运维脚本默认只打生产栈**，操作测试栈必须显式指定目标：

```bash
cd deploy
STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./scripts/backup.sh --dry-run
STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./scripts/restore.sh --db backups/db_fault-test_xxx.dump
STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./scripts/harden.sh --check
STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./scripts/install-cron.sh
```

每个脚本开头都会打印目标栈（env / compose 项目 / 容器前缀 / 数据目录）。只给 `STACK_ENV_FILE` 而不给 `STACK_PROJECT` 时，脚本按容器前缀推导项目名（`.env.test` → `fault-test`），推导结果与容器前缀矛盾或 env 是测试文件却仍是生产前缀时直接拒绝，不会静默回落到生产项目。

`restore.sh` 这类破坏性操作在交互终端要求输入 `y`；非交互（cron / CI / `ssh -T`）默认拒绝，必须显式 `--yes` 或 `STACK_ASSUME_YES=1`。两栈的 cron 条目各有独立标记，互不覆盖。

**演示数据必须同时指定三处目标**，只改 `--base-url` 会被守卫拦下——那正是「清库清在测试栈、数据写进生产」的错配路径：

```bash
SEED_ENV_FILE=deploy/.env.test SEED_COMPOSE_PROJECT=fault-test \
  .venv/bin/python scripts/dev/seed_demo.py --reset --activity \
  --base-url http://127.0.0.1:8080

SEED_ENV_FILE=deploy/.env.test SEED_COMPOSE_PROJECT=fault-test \
  .venv/bin/python scripts/dev/demo_inventory.py --reset \
  --base-url http://127.0.0.1:8080
```

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

前端开发服务器（`/api` 与 `/uploads` 代理到 8000）：

```bash
cd frontend && npm install && npm run dev
```

详见 `docs/开发环境搭建.md`。

## 常用命令

| 目的 | 命令 |
|---|---|
| 一键部署 / 体检 | `cd deploy && ./deploy.sh` / `./deploy.sh --check` |
| 后端测试 | `.venv/bin/python -m pytest backend/tests -q` |
| 前端单测 | `cd frontend && npm run test` |
| 前端 lint | `cd frontend && npm run lint` |
| 端到端冒烟 | `cd frontend && npm run e2e` |
| 逐屏走查截图 | `cd frontend && npm run e2e:walk` |
| 移动端三视口验收 | `cd frontend && npm run e2e:mobile` |
| 硬编码中文检查 | `python scripts/dev/check_i18n.py` |
| 文档链接检查 | `python scripts/dev/check_links.py` |
| 测试函数重名检查 | `python scripts/dev/check_duplicate_tests.py` |
| 环境自检 / 拉镜像 | `bash scripts/dev/check_env.sh --pull` |
| 校验建表脚本 | `node scripts/dev/verify_schema.mjs` |
| 写入演示数据（幂等） | `.venv/bin/python scripts/dev/seed_demo.py --via-sql --activity` |
| 重置演示数据 | `.venv/bin/python scripts/dev/seed_demo.py --reset --via-sql --activity` |
| 清理上传残留 | `cd deploy && ./scripts/cleanup-uploads.sh`（预演，加 `--apply` 执行） |
| 清理过期审计 | `cd deploy && ./scripts/cleanup-audit.sh`（默认保留 190 天，加 `--apply`） |

前端测试直接跑某个文件：`cd frontend && npx vitest run src/views/public/Home.spec.js`。

## 文档入口

先看这三份，再按需翻其他：

- `docs/README.md` —— 文档总索引
- `docs/02-技术设计/系统架构设计.md` —— 分层、鉴权、会话与空闲超时（§8.3）
- `docs/05-评估审查/04-修复记录.md` —— 改过什么、为什么改、还剩什么

## 约定

- **路径一律以仓库根为基准**写（如 `docs/02-技术设计/API接口契约.md`、`deploy/schema.sql`）
- 分支：`main` 受保护，开发在 `feat/*`，修复在 `fix/*`
- 提交：`<type>: <subject>`，type ∈ feat / fix / docs / chore / test / refactor
- 密钥只放 `deploy/.env`（已 gitignore），仓库内只留 `.env.example`
- 前端文案只走 `src/locales/{zh-CN,en-US}/`，禁止拼 key；新增错误码需同步两边语言包与契约 §7
- 清登录痕迹统一走 `frontend/src/utils/session.js#clearAuthLocal()`，不要各处手写 `removeItem`

## 技术栈

后端 FastAPI + SQLAlchemy 2.0 + Pydantic v2 + PostgreSQL 15；前端 Vue 3 + Vite +
Element Plus + ECharts；Nginx 同源反代；Docker Compose 编排；单机 4 核 8G 可跑，
全私有化部署，无外部依赖。
