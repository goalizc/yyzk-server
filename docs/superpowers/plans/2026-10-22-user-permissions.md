# 用户管理、角色权限与产品线数据权限 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有系统上落地四角色权限、用户管理、产品线与工单数据范围、临时授权，并保证部署与恢复路径可重复执行。

**Architecture:** 权限码与角色模板集中在 `backend/app/core/permissions.py`，接口用 `Depends(require(...))` 声明；数据范围只作用于工单三个接口，由 `backend/app/services/ticket_scope.py` 统一计算；产品线成为一等实体，`products.line_id` 非空；临时授权按人发放、带到期时间；新增 `schema_migrations` 与 `migrate` 一次性服务，部署顺序改为「db 就绪 → 迁移 → 启动后端」。

**Tech Stack:** FastAPI、SQLAlchemy 2、PostgreSQL 15、pytest（SQLite 内存库）、Vue 3 + Element Plus、Vitest、Docker Compose。

**设计来源:** `docs/superpowers/specs/2026-10-22-user-permissions-design.md`

---

## 文件结构（先锁边界）

| 文件 | 责任 |
|---|---|
| `deploy/scripts/migrate.py` | 按版本执行 `deploy/migrations/*.sql`，记录到 `schema_migrations` |
| `deploy/migrations/001_user_permissions.sql` | 本次唯一迁移：产品线、授权表、角色约束 |
| `backend/app/core/permissions.py` | 权限码、角色模板、数据范围、依赖闭包、`require()` |
| `backend/app/services/ticket_scope.py` | 工单可见性、改派候选人校验 |
| `backend/app/models/product_line.py` | `ProductLine` 模型 |
| `backend/app/models/user.py` | `User` + `UserProductLine` + `UserPermissionGrant` |
| `backend/app/schemas/user.py` | 用户管理与临时授权的请求/响应 |
| `backend/app/schemas/product_line.py` | 产品线请求/响应 |
| `backend/app/api/admin_users.py` | 用户、授权、候选人接口 |
| `backend/app/api/admin_product_lines.py` | 产品线 CRUD |
| `frontend/src/utils/permissions.js` | 前端权限集合与 `hasPermission` |
| `frontend/src/views/admin/users/UserList.vue` | P-18 用户管理页 |
| `frontend/src/views/admin/product-lines/ProductLineList.vue` | P-19 产品线管理页 |

---

## Task 1: 迁移机制与部署顺序

**Files:**
- Create: `deploy/scripts/migrate.py`
- Create: `deploy/migrations/.gitkeep`（迁移目录占位）
- Modify: `deploy/schema.sql`
- Modify: `deploy/docker-compose.yml`
- Modify: `deploy/deploy.sh:246-337`
- Modify: `deploy/scripts/restore.sh`（末尾）
- Test: `backend/tests/test_migrate.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_migrate.py
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("migrate", ROOT / "deploy/scripts/migrate.py")


def _load():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


def test_pending_versions_filters_applied_and_sorts(tmp_path):
    (tmp_path / "002_second.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "003_third.sql").write_text("SELECT 1;", encoding="utf-8")

    pending = _load().pending_versions(tmp_path, {"002_second"})

    assert [path.name for path in pending] == ["001_first.sql", "003_third.sql"]
```

- [ ] **Step 2: 运行并确认失败**

Run: `pytest backend/tests/test_migrate.py -v`
Expected: FAIL，`FileNotFoundError: deploy/scripts/migrate.py`

- [ ] **Step 3: 写迁移执行器**

```python
#!/usr/bin/env python3
"""按文件名顺序执行 deploy/migrations/*.sql，已执行版本跳过。

用法：
    docker compose run --rm migrate
环境变量：
    DATABASE_URL     必填
    MIGRATION_DIR    默认 /app/migrations
"""

from __future__ import annotations

import os
import pathlib
import sys

from sqlalchemy import create_engine, text

MIGRATION_DIR = pathlib.Path(os.getenv("MIGRATION_DIR", "/app/migrations"))

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    VARCHAR(50) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def pending_versions(directory: pathlib.Path, applied: set[str]) -> list[pathlib.Path]:
    """返回尚未执行的迁移文件，按文件名升序。"""
    files = sorted(directory.glob("*.sql"))
    return [path for path in files if path.stem not in applied]


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[migrate] 缺少环境变量 DATABASE_URL", file=sys.stderr)
        return 2

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text(_CREATE_TABLE))
        applied = {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}

    pending = pending_versions(MIGRATION_DIR, applied)
    if not pending:
        print("[migrate] 没有待执行的迁移")
        return 0

    for path in pending:
        sql = path.read_text(encoding="utf-8")
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(sql)
                conn.execute(
                    text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                    {"version": path.stem},
                )
        except Exception as exc:  # noqa: BLE001 迁移失败必须整体退出
            print(f"[migrate] 执行失败 {path.name}: {exc}", file=sys.stderr)
            return 1
        print(f"[migrate] 已执行 {path.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_migrate.py -v`
Expected: PASS

- [ ] **Step 5: schema.sql 加入迁移登记表**

在 `deploy/schema.sql` 的扩展段之后、`users` 表之前加入：

```sql
-- ------------------------------------------------------------
-- 0. 迁移登记（已有环境升级用；全新库由本脚本直接建到最新结构）
-- ------------------------------------------------------------
CREATE TABLE schema_migrations (
    version    VARCHAR(50) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO schema_migrations (version) VALUES ('000_baseline');
```

文件末尾追加（新库不重复执行随包迁移）：

```sql
INSERT INTO schema_migrations (version) VALUES ('001_user_permissions');
```

- [ ] **Step 6: compose 增加 migrate 一次性服务**

在 `deploy/docker-compose.yml` 的 `init` 服务后追加，构建参数与 `init` 完全一致：

```yaml
  # 数据库迁移: docker compose run --rm migrate
  migrate:
    build:
      context: ..
      dockerfile: backend/Dockerfile
      args:
        PYTHON_IMAGE: ${PYTHON_IMAGE:-python:3.12-slim}
        PIP_INDEX_URL: ${PIP_INDEX_URL:-https://pypi.org/simple}
        PIP_TRUSTED_HOST: ${PIP_TRUSTED_HOST:-pypi.org}
    profiles: ["migrate"]
    environment:
      DATABASE_URL: postgresql+psycopg2://${DB_USER:-fault}:${DB_PASSWORD}@db:5432/${DB_NAME:-fault_db}
      MIGRATION_DIR: /app/migrations
      TZ: ${TZ:-Asia/Shanghai}
    volumes:
      - ./scripts:/app/scripts:ro
      - ./migrations:/app/migrations:ro
    entrypoint: ["python", "/app/scripts/migrate.py"]
    depends_on:
      db:
        condition: service_healthy
    networks:
      - fault-net
```

- [ ] **Step 7: deploy.sh 调整启动顺序**

把 `step "启动服务"` 的非 check 分支改为下述顺序，保留原日志与错误提示：

```bash
  # 1) 只起 db，先完成迁移，避免新代码对旧表
  set +e
  docker compose up -d db >/tmp/deploy_up.log 2>&1
  UP_RC=$?
  set -e
  if [[ "$UP_RC" != "0" ]]; then
    tail -15 /tmp/deploy_up.log >&2
    die "启动数据库失败，详见上面的输出"
  fi

  DB_DEADLINE=$(( SECONDS + 120 ))
  until docker compose ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep -q "^fault-db healthy"; do
    if (( SECONDS >= DB_DEADLINE )); then
      docker compose logs --tail=50 db
      die "数据库未在 120 秒内就绪"
    fi
    sleep 2
  done

  # 迁移会删除 products.category，不可逆；先备份，失败即中止
  if [[ -x scripts/backup.sh ]]; then
    set +e
    ./scripts/backup.sh >/tmp/deploy_backup.log 2>&1
    BK_RC=$?
    set -e
    tail -2 /tmp/deploy_backup.log
    if [[ "$BK_RC" != "0" ]]; then
      tail -20 /tmp/deploy_backup.log >&2
      die "迁移前备份失败，已中止（本次迁移会删除 products.category）"
    fi
    rm -f /tmp/deploy_backup.log
  fi

  set +e
  docker compose run --rm -T migrate >/tmp/deploy_migrate.log 2>&1
  MIG_RC=$?
  set -e
  tail -5 /tmp/deploy_migrate.log
  if [[ "$MIG_RC" != "0" ]]; then
    tail -30 /tmp/deploy_migrate.log >&2
    die "数据库迁移失败，详见上面的输出"
  fi
  rm -f /tmp/deploy_migrate.log

  # 2) 迁移完成后再起 backend/frontend
  set +e
  docker compose up -d >/tmp/deploy_up.log 2>&1
  UP_RC=$?
  set -e
  tail -3 /tmp/deploy_up.log
  if [[ "$UP_RC" != "0" ]]; then
    tail -15 /tmp/deploy_up.log >&2
    rm -f /tmp/deploy_up.log
    die "启动服务失败，详见上面的输出。"
  fi
  rm -f /tmp/deploy_up.log
```

- [ ] **Step 8: restore.sh 恢复后执行迁移**

在行数自检通过之后、脚本结束之前追加：

```bash
log "执行数据库迁移（备份可能来自旧版本）"
docker compose run --rm -T migrate
```

- [ ] **Step 9: 提交**

```bash
git add deploy/scripts/migrate.py deploy/migrations/.gitkeep deploy/schema.sql \
  deploy/docker-compose.yml deploy/deploy.sh deploy/scripts/restore.sh \
  backend/tests/test_migrate.py
git commit -m "feat(deploy): 引入 schema_migrations 与 migrate 服务，部署先迁移后起服"
```

---

## Task 2: 产品线、用户授权表与 ORM

**Files:**
- Create: `backend/app/models/product_line.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/product.py`
- Modify: `backend/app/models/__init__.py`
- Create: `deploy/migrations/001_user_permissions.sql`
- Modify: `deploy/schema.sql`
- Test: `backend/tests/test_models_permissions.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_models_permissions.py
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Product, ProductLine, UserPermissionGrant, UserProductLine


def test_product_line_name_property(db, make_user):
    line = ProductLine(name="扫地机")
    db.add(line)
    db.flush()
    product = Product(name="扫地机器人", model="X1", line_id=line.id)
    db.add(product)
    db.commit()

    assert product.line.name == "扫地机"
    assert product.line_name == "扫地机"


def test_user_product_line_and_grant_rows(db):
    user = make_user(db)
    line = ProductLine(name="净化器")
    db.add(line)
    db.flush()
    db.add(UserProductLine(user_id=user.id, line_id=line.id))
    db.add(
        UserPermissionGrant(
            user_id=user.id,
            permission="fault:write",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            reason="临时接手知识库",
        )
    )
    db.commit()

    assert db.scalar(select(UserProductLine).where(UserProductLine.user_id == user.id)) is not None
    assert db.scalar(select(UserPermissionGrant).where(UserPermissionGrant.user_id == user.id)) is not None
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest backend/tests/test_models_permissions.py -v`
Expected: FAIL，`ImportError: cannot import name 'ProductLine'`

- [ ] **Step 3: 新建 ProductLine 模型**

```python
# backend/app/models/product_line.py
"""产品线（product_lines）。产品归属产品线，客服的数据范围按产品线计算。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProductLine(Base):
    __tablename__ = "product_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    products: Mapped[list["Product"]] = relationship(  # noqa: F821
        back_populates="line", order_by="Product.sort_order"
    )
```

- [ ] **Step 4: 重写 User 模型，加入两张关联表**

```python
# backend/app/models/user.py
"""后台用户、产品线授权与临时权限授权。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    real_name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="agent")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    product_lines: Mapped[list["UserProductLine"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    grants: Mapped[list["UserPermissionGrant"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserPermissionGrant.user_id",
    )


class UserProductLine(Base):
    __tablename__ = "user_product_lines"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("product_lines.id", ondelete="CASCADE"), primary_key=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="product_lines")
    line: Mapped["ProductLine"] = relationship()  # noqa: F821


class UserPermissionGrant(Base):
    __tablename__ = "user_permission_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    granted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="grants", foreign_keys=[user_id])
```

- [ ] **Step 5: Product 模型加入 line_id 与 line_name**

```python
# backend/app/models/product.py 中 Product 类内
    line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("product_lines.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    line: Mapped["ProductLine"] = relationship(back_populates="products")  # noqa: F821

    @property
    def line_name(self) -> str | None:
        return self.line.name if self.line else None
```

同时删除 `category` 字段。

- [ ] **Step 6: 注册模型**

```python
# backend/app/models/__init__.py
from app.models.fault import Fault
from app.models.part import Part
from app.models.product import Product
from app.models.product_line import ProductLine
from app.models.query_log import QueryLog
from app.models.ticket import Ticket, TicketStatusLog
from app.models.user import User, UserPermissionGrant, UserProductLine

__all__ = [
    "Fault", "Part", "Product", "ProductLine", "QueryLog",
    "Ticket", "TicketStatusLog", "User", "UserPermissionGrant", "UserProductLine",
]
```

- [ ] **Step 7: 写迁移 SQL**

```sql
-- deploy/migrations/001_user_permissions.sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    VARCHAR(50) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE product_lines (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(50) NOT NULL UNIQUE,
    sort_order INT NOT NULL DEFAULT 0,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_product_lines (
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    line_id    INT NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, line_id)
);
CREATE INDEX idx_user_product_lines_line ON user_product_lines(line_id);

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

ALTER TABLE products ADD COLUMN line_id INT REFERENCES product_lines(id) ON DELETE RESTRICT;

INSERT INTO product_lines (name)
SELECT DISTINCT TRIM(category) FROM products
WHERE category IS NOT NULL AND TRIM(category) <> ''
ON CONFLICT (name) DO NOTHING;

INSERT INTO product_lines (name)
SELECT '未分类'
WHERE EXISTS (
    SELECT 1 FROM products WHERE category IS NULL OR TRIM(category) = ''
)
ON CONFLICT (name) DO NOTHING;

UPDATE products p
SET line_id = l.id
FROM product_lines l
WHERE l.name = TRIM(p.category);

UPDATE products p
SET line_id = (SELECT id FROM product_lines WHERE name = '未分类')
WHERE p.line_id IS NULL;

ALTER TABLE products ALTER COLUMN line_id SET NOT NULL;
CREATE INDEX idx_products_line ON products(line_id);
ALTER TABLE products DROP COLUMN category;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
UPDATE users SET role = 'super_admin' WHERE role = 'admin';
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('super_admin', 'supervisor', 'agent', 'auditor'));
```

- [ ] **Step 8: schema.sql 同步到最新结构**

按下面顺序调整 `deploy/schema.sql`：

1. 在 users 表前插入 Task 1 的 `schema_migrations` 段。
2. 新建 `product_lines` 段（放在 `products` 之前）。
3. `products` 表用 `line_id INT NOT NULL REFERENCES product_lines(id) ON DELETE RESTRICT` 替换 `category VARCHAR(50)`，并加 `CREATE INDEX idx_products_line ON products(line_id);`。
4. 在 users 段后追加 `user_product_lines`、`user_permission_grants` 两段（与迁移 SQL 一致）。
5. users 的 CHECK 改为四个值。
6. 文件末尾保留 Task 1 的迁移版本登记。

- [ ] **Step 9: 更新 init_admin.py 的角色**

`deploy/scripts/init_admin.py` 三处必须改，否则全新部署创建的管理员会违反 CHECK 或没有任何权限：

```python
# 创建管理员的 INSERT：固定值 'admin' 改为 'super_admin'
INSERT INTO users (username, password_hash, real_name, role, is_active)
VALUES (:u, :p, :r, 'super_admin', TRUE)

# argparse 的 --role
p_user.add_argument(
    "--role",
    default="agent",
    choices=["super_admin", "supervisor", "agent", "auditor"],
    help="角色，默认 agent",
)
```

同时删除文件头与 `cmd_user` 文档里"一期没有用户管理界面""不区分权限"的过期描述。

- [ ] **Step 10: 运行模型测试**

Run: `pytest backend/tests/test_models_permissions.py -v`
Expected: PASS

- [ ] **Step 11: 提交**

```bash
git add backend/app/models backend/tests/test_models_permissions.py \
  deploy/migrations/001_user_permissions.sql deploy/schema.sql deploy/scripts/init_admin.py
git commit -m "feat(db): 产品线与用户授权表，products 改为归属产品线"
```

---

## Task 3: 权限核心模块

**Files:**
- Create: `backend/app/core/permissions.py`
- Test: `backend/tests/test_permissions.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_permissions.py
from datetime import datetime, timedelta, timezone

import pytest

from app.core.permissions import (
    ALL_PERMISSIONS,
    LINES,
    TICKET_ASSIGN,
    TICKET_READ,
    TICKET_WRITE,
    USER_WRITE,
    data_scope,
    effective_permissions,
    expand,
    role_permissions,
)
from app.models import UserPermissionGrant


def test_role_matrix_is_closed():
    for role in ("super_admin", "supervisor", "agent", "auditor"):
        assert role_permissions(role) == expand(role_permissions(role))


def test_agent_permissions_exact():
    assert role_permissions("agent") == {"ticket:read", "ticket:write", "fault:read"}
    assert data_scope(type("U", (), {"role": "agent"})()) == LINES


def test_closure_pulls_in_dependencies():
    assert expand({TICKET_ASSIGN}) == {TICKET_ASSIGN, TICKET_READ, TICKET_WRITE}
    assert {"fault:read", "product:read", "part:read", "upload:write"} <= expand({"fault:write"})


def test_active_grant_is_added_and_expired_is_ignored(db, make_user):
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


def test_revoked_grant_is_ignored(db, make_user):
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


def test_user_write_not_grantable():
    from app.core.permissions import grantable_permissions

    assert USER_WRITE not in grantable_permissions()
    assert grantable_permissions() == ALL_PERMISSIONS - {USER_WRITE}
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest backend/tests/test_permissions.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.core.permissions'`

- [ ] **Step 3: 实现权限模块**

```python
# backend/app/core/permissions.py
"""权限码、角色模板、数据范围与生效权限。

权限是代码行为的一部分，不建数据库表；角色固定四种。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.exceptions import BusinessError
from app.database import get_db
from app.models import User, UserPermissionGrant

# ---- 数据范围 ----
ALL = "ALL"
LINES = "LINES"

# ---- 权限码 ----
TICKET_READ = "ticket:read"
TICKET_WRITE = "ticket:write"
TICKET_ASSIGN = "ticket:assign"
PRODUCT_READ = "product:read"
PRODUCT_WRITE = "product:write"
PART_READ = "part:read"
PART_WRITE = "part:write"
FAULT_READ = "fault:read"
FAULT_WRITE = "fault:write"
UPLOAD_WRITE = "upload:write"
STATS_READ = "stats:read"
USER_READ = "user:read"
USER_WRITE = "user:write"
PRODUCT_LINE_READ = "product_line:read"
PRODUCT_LINE_WRITE = "product_line:write"

ALL_PERMISSIONS = frozenset(
    {
        TICKET_READ, TICKET_WRITE, TICKET_ASSIGN,
        PRODUCT_READ, PRODUCT_WRITE, PART_READ, PART_WRITE,
        FAULT_READ, FAULT_WRITE, UPLOAD_WRITE, STATS_READ,
        USER_READ, USER_WRITE, PRODUCT_LINE_READ, PRODUCT_LINE_WRITE,
    }
)

ROLE_NAMES = {
    "super_admin": "超级管理员",
    "supervisor": "售后主管",
    "agent": "一线客服",
    "auditor": "只读审计",
}

_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "super_admin": ALL_PERMISSIONS,
    "supervisor": ALL_PERMISSIONS - {USER_READ, USER_WRITE},
    "agent": frozenset({TICKET_READ, TICKET_WRITE, FAULT_READ}),
    "auditor": frozenset(
        {
            TICKET_READ, PRODUCT_READ, PART_READ, FAULT_READ,
            STATS_READ, USER_READ, PRODUCT_LINE_READ,
        }
    ),
}

_DATA_SCOPE: dict[str, str] = {
    "super_admin": ALL,
    "supervisor": ALL,
    "agent": LINES,
    "auditor": ALL,
}

_DEPENDENCIES: dict[str, frozenset[str]] = {
    TICKET_WRITE: frozenset({TICKET_READ}),
    TICKET_ASSIGN: frozenset({TICKET_READ, TICKET_WRITE}),
    FAULT_WRITE: frozenset({FAULT_READ, PRODUCT_READ, PART_READ, UPLOAD_WRITE}),
    PRODUCT_WRITE: frozenset({PRODUCT_READ}),
    PART_WRITE: frozenset({PART_READ, PRODUCT_READ}),
    PRODUCT_LINE_WRITE: frozenset({PRODUCT_LINE_READ}),
    USER_WRITE: frozenset({USER_READ}),
}


def expand(permissions: Iterable[str]) -> frozenset[str]:
    """按依赖闭包补齐权限，直到不再变化。"""
    result = set(permissions)
    changed = True
    while changed:
        changed = False
        for permission in tuple(result):
            for dependency in _DEPENDENCIES.get(permission, frozenset()):
                if dependency not in result:
                    result.add(dependency)
                    changed = True
    return frozenset(result)


def role_permissions(role: str) -> frozenset[str]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


def role_scope(role: str) -> str:
    return _DATA_SCOPE.get(role, LINES)


def data_scope(user: User) -> str:
    return role_scope(user.role)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def active_grants(db: Session, user_id: int) -> list[str]:
    """未收回、未过期的临时授权。按 Python 侧比较，兼容 SQLite 单测。"""
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(UserPermissionGrant).where(
            UserPermissionGrant.user_id == user_id,
            UserPermissionGrant.revoked_at.is_(None),
        )
    ).all()
    return [row.permission for row in rows if _as_utc(row.expires_at) > now]


def effective_permissions(db: Session, user: User) -> frozenset[str]:
    if not user.is_active:
        return frozenset()
    return expand(role_permissions(user.role) | set(active_grants(db, user.id)))


def grantable_permissions() -> frozenset[str]:
    """可临时授予的权限：user:write 会变成提权入口，永远排除。"""
    return ALL_PERMISSIONS - {USER_WRITE}


def current_permissions(user: User, db: Session) -> list[str]:
    return sorted(effective_permissions(db, user))


def require(permission: str) -> Callable[..., User]:
    """FastAPI 依赖：无权限返回 403 PERMISSION_DENIED。"""

    def dependency(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if permission not in effective_permissions(db, user):
            raise BusinessError("PERMISSION_DENIED", "无权限执行此操作", 403)
        return user

    return dependency
```

- [ ] **Step 4: 运行测试**

Run: `pytest backend/tests/test_permissions.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/permissions.py backend/tests/test_permissions.py
git commit -m "feat(authz): 权限码、角色模板与临时授权闭包"
```

---

## Task 4: 权限接入现有接口

**Files:**
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/api/admin_faults.py`
- Modify: `backend/app/api/admin_tickets.py`
- Modify: `backend/app/api/stats.py`
- Modify: `backend/tests/conftest.py:88-107`
- Modify: `backend/tests/test_auth.py:23-25`
- Test: `backend/tests/test_permission_endpoints.py`

- [ ] **Step 1: 先把测试夹具迁到新角色**

`backend/tests/conftest.py` 的 `make_user` 默认值改为：

```python
def make_user(
    db: Session,
    username: str = "admin",
    password: str = DEFAULT_PASSWORD,
    *,
    real_name: str = "系统管理员",
    role: str = "super_admin",
    is_active: bool = True,
) -> User:
```

`backend/tests/test_auth.py` 中 `"role": "admin"` 改为 `"role": "super_admin"`。

- [ ] **Step 2: 写失败测试**

```python
# backend/tests/test_permission_endpoints.py
import pytest

from app.core.permissions import effective_permissions
from app.models import User
from tests.conftest import auth_headers, login, make_user

READ_CASES = [
    ("/api/admin/products", "product:read"),
    ("/api/admin/tickets", "ticket:read"),
    ("/api/admin/faults", "fault:read"),
    ("/api/admin/stats/overview", "stats:read"),
]


@pytest.mark.parametrize("role", ["super_admin", "supervisor", "agent", "auditor"])
@pytest.mark.parametrize("path,permission", READ_CASES)
def test_read_endpoint_permission(client, db, role, path, permission):
    user = make_user(db, username=role, role=role)
    headers = auth_headers(login(client, role)["access_token"])

    response = client.get(path, headers=headers)

    if permission in effective_permissions(db, user):
        assert response.status_code != 403, response.text
    else:
        assert response.status_code == 403
        assert response.json()["code"] == "PERMISSION_DENIED"


def test_agent_cannot_call_fault_write(client, db):
    make_user(db, username="agent1", role="agent")
    headers = auth_headers(login(client, "agent1")["access_token"])

    response = client.post("/api/admin/faults", json={}, headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_auditor_can_read_but_not_write_tickets(client, db):
    make_user(db, username="auditor1", role="auditor")
    headers = auth_headers(login(client, "auditor1")["access_token"])

    assert client.get("/api/admin/tickets", headers=headers).status_code == 200
    response = client.put("/api/admin/tickets/99999", json={"remark": "x"}, headers=headers)
    assert response.status_code == 403
```

- [ ] **Step 3: 运行确认失败**

Run: `pytest backend/tests/test_permission_endpoints.py -v`
Expected: FAIL，agent 调产品列表返回 200 而不是 403

- [ ] **Step 4: 替换依赖**

按以下映射，把各路由函数签名里的 `_: User = Depends(get_current_user)` 或 `user: User = Depends(get_current_user)` 替换为 `Depends(require(...))`，并从 `app.core.permissions` 导入对应常量：

| 文件 | 接口 | 权限 |
|---|---|---|
| `admin.py` | `GET /products` | `PRODUCT_READ` |
| `admin.py` | `POST/PUT/DELETE /products` | `PRODUCT_WRITE` |
| `admin.py` | `GET /parts` | `PART_READ` |
| `admin.py` | `POST/PUT/DELETE /parts` | `PART_WRITE` |
| `admin.py` | `POST/DELETE /upload` | `UPLOAD_WRITE` |
| `admin_faults.py` | `GET /faults`、`GET /faults/{id}` | `FAULT_READ` |
| `admin_faults.py` | `POST/PUT/DELETE /faults` | `FAULT_WRITE` |
| `admin_tickets.py` | `GET /tickets`、`GET /tickets/{id}` | `TICKET_READ` |
| `admin_tickets.py` | `PUT /tickets/{id}` | `TICKET_WRITE` |
| `stats.py` | 三个看板接口 | `STATS_READ` |

`create_fault` 还要保留 `user` 参数用于 `created_by`：

```python
from app.core.permissions import FAULT_WRITE, require
...
def create_fault(
    payload: FaultCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require(FAULT_WRITE)),
) -> FaultAdminDetail:
```

- [ ] **Step 5: 运行测试**

Run: `pytest backend/tests/test_permission_endpoints.py backend/tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 6: 清理过期注释**

`backend/app/core/deps.py` 文件头"一期 users.role 有 admin/agent 两个值但不参与鉴权判断"的整段注释删除，替换为：

```python
"""依赖注入：数据库会话与当前登录用户。

鉴权在 app.core.permissions 中完成，本模块只负责识别用户与停用校验。
"""
```

`backend/app/models/user.py` 的"一期不做用户管理界面"注释已在 Task 2 重写时删除。

- [ ] **Step 7: 提交**

```bash
git add backend/app/api backend/tests/conftest.py backend/tests/test_auth.py \
  backend/tests/test_permission_endpoints.py
git commit -m "feat(authz): 现有后台接口全部按权限码鉴权"
```

---

## Task 5: 登录与 /auth/me 下发权限

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/api/auth.py`
- Test: `backend/tests/test_auth_permissions.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_auth_permissions.py
from app.core.permissions import TICKET_READ, TICKET_WRITE
from tests.conftest import auth_headers, login, make_user


def test_login_returns_permissions(client, db):
    make_user(db, username="agent1", role="agent")

    body = login(client, "agent1")

    assert set(body["permissions"]) == {"ticket:read", "ticket:write", "fault:read"}


def test_me_returns_live_permissions(client, db):
    user = make_user(db, username="agent1", role="agent")
    headers = auth_headers(login(client, "agent1")["access_token"])

    user.role = "supervisor"
    db.commit()

    body = client.get("/api/auth/me", headers=headers).json()
    assert "stats:read" in body["permissions"]
    assert TICKET_READ in body["permissions"]
    assert TICKET_WRITE in body["permissions"]
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest backend/tests/test_auth_permissions.py -v`
Expected: FAIL，`KeyError: 'permissions'`

- [ ] **Step 3: 修改 schema**

```python
# backend/app/schemas/auth.py 中
class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime = Field(description="带 +08:00 偏移的 ISO 8601 时间")
    user: UserOut
    permissions: list[str] = Field(default_factory=list, description="生效权限码，已展开依赖")


class MeResponse(BaseModel):
    user: UserOut
    permissions: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: 修改登录与新增 /me**

```python
# backend/app/api/auth.py
from app.core.permissions import current_permissions
from app.schemas.auth import LoginResponse, MeResponse, UserOut

# login() 的返回改为：
    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserOut.model_validate(user),
        permissions=current_permissions(user, db),
    )


@router.get("/me", response_model=MeResponse, summary="当前账号与生效权限")
def me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    return MeResponse(
        user=UserOut.model_validate(user),
        permissions=current_permissions(user, db),
    )
```

- [ ] **Step 5: 运行测试**

Run: `pytest backend/tests/test_auth_permissions.py backend/tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/auth.py backend/app/api/auth.py backend/tests/test_auth_permissions.py
git commit -m "feat(auth): 登录与 /auth/me 返回生效权限码"
```

---

## Task 6: 产品线接口与产品接口改造

**Files:**
- Create: `backend/app/schemas/product_line.py`
- Create: `backend/app/api/admin_product_lines.py`
- Modify: `backend/app/schemas/product.py`
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/api/public.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_products.py`
- Test: `backend/tests/test_product_lines.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_product_lines.py
from tests.conftest import auth_headers, login, make_user


def _headers(client, db):
    make_user(db, username="admin")
    return auth_headers(login(client, "admin")["access_token"])


def test_create_and_list_line(client, db):
    headers = _headers(client, db)

    created = client.post(
        "/api/admin/product-lines", json={"name": "扫地机", "sort_order": 1}, headers=headers
    )
    assert created.status_code == 201
    body = client.get("/api/admin/product-lines", headers=headers).json()
    assert body["items"][0]["name"] == "扫地机"


def test_duplicate_line_name(client, db):
    headers = _headers(client, db)
    client.post("/api/admin/product-lines", json={"name": "扫地机"}, headers=headers)

    response = client.post("/api/admin/product-lines", json={"name": "扫地机"}, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "LINE_NAME_DUPLICATED"


def test_delete_line_referenced_by_product(client, db):
    headers = _headers(client, db)
    line = client.post("/api/admin/product-lines", json={"name": "扫地机"}, headers=headers).json()
    client.post(
        "/api/admin/products",
        json={"name": "扫地机器人", "model": "X1", "line_id": line["id"]},
        headers=headers,
    )

    response = client.delete(f"/api/admin/product-lines/{line['id']}", headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "DELETE_BLOCKED"


def test_product_requires_line(client, db):
    headers = _headers(client, db)

    response = client.post(
        "/api/admin/products", json={"name": "扫地机器人", "model": "X1"}, headers=headers
    )

    assert response.status_code == 422


def test_product_response_has_line_name(client, db):
    headers = _headers(client, db)
    line = client.post("/api/admin/product-lines", json={"name": "扫地机"}, headers=headers).json()

    product = client.post(
        "/api/admin/products",
        json={"name": "扫地机器人", "model": "X1", "line_id": line["id"]},
        headers=headers,
    ).json()

    assert product["line_id"] == line["id"]
    assert product["line_name"] == "扫地机"
    assert "category" not in product
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest backend/tests/test_product_lines.py -v`
Expected: FAIL，404（接口不存在）

- [ ] **Step 3: 新建产品线 schema**

```python
# backend/app/schemas/product_line.py
"""产品线请求/响应。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import AppDateTime


class ProductLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort_order: int
    is_active: bool
    product_count: int = 0
    created_at: AppDateTime
    updated_at: AppDateTime


class ProductLineList(BaseModel):
    items: list[ProductLineOut]


class ProductLineCreate(BaseModel):
    name: str = Field(max_length=50, examples=["扫地机"])
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("产品线名称不能为空")
        return value


class ProductLineUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=50)
    sort_order: int | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("产品线名称不能为空")
        return value
```

- [ ] **Step 4: 新建产品线路由**

```python
# backend/app/api/admin_product_lines.py
"""产品线 CRUD。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.exceptions import BusinessError
from app.core.permissions import PRODUCT_LINE_READ, PRODUCT_LINE_WRITE, require
from app.database import get_db
from app.models import Product, ProductLine, User
from app.schemas.common import ErrorBody, SuccessResponse
from app.schemas.product_line import ProductLineCreate, ProductLineList, ProductLineOut, ProductLineUpdate

router = APIRouter()


def _counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Product.line_id, func.count(Product.id)).group_by(Product.line_id)
    ).all()
    return {line_id: count for line_id, count in rows}


def _to_out(line: ProductLine, counts: dict[int, int]) -> ProductLineOut:
    return ProductLineOut(
        id=line.id,
        name=line.name,
        sort_order=line.sort_order,
        is_active=line.is_active,
        product_count=counts.get(line.id, 0),
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


@router.get("/product-lines", response_model=ProductLineList, summary="产品线列表")
def list_lines(
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require(PRODUCT_LINE_READ)),
) -> ProductLineList:
    stmt = select(ProductLine).order_by(ProductLine.sort_order, ProductLine.id)
    if is_active is not None:
        stmt = stmt.where(ProductLine.is_active.is_(is_active))
    counts = _counts(db)
    return ProductLineList(items=[_to_out(line, counts) for line in db.scalars(stmt)])


@router.post(
    "/product-lines",
    status_code=201,
    response_model=ProductLineOut,
    summary="新建产品线",
    responses={409: {"model": ErrorBody, "description": "名称重复"}},
)
def create_line(
    payload: ProductLineCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require(PRODUCT_LINE_WRITE)),
) -> ProductLineOut:
    line = ProductLine(**payload.model_dump())
    db.add(line)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError("LINE_NAME_DUPLICATED", f"产品线 {payload.name} 已存在", 409) from exc
    db.refresh(line)
    return _to_out(line, {})


@router.put(
    "/product-lines/{line_id}",
    response_model=ProductLineOut,
    summary="修改产品线",
)
def update_line(
    line_id: int,
    payload: ProductLineUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require(PRODUCT_LINE_WRITE)),
) -> ProductLineOut:
    line = db.get(ProductLine, line_id)
    if line is None:
        raise BusinessError("NOT_FOUND", "产品线不存在", 404)

    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is None:
        data.pop("name", None)
    for field, value in data.items():
        setattr(line, field, value)
    line.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError(
            "LINE_NAME_DUPLICATED", f"产品线 {data.get('name', '')} 已存在", 409
        ) from exc
    db.refresh(line)
    return _to_out(line, _counts(db))


@router.delete(
    "/product-lines/{line_id}",
    response_model=SuccessResponse,
    summary="删除产品线",
    responses={409: {"model": ErrorBody, "description": "仍有产品引用"}},
)
def delete_line(
    line_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(PRODUCT_LINE_WRITE)),
) -> SuccessResponse:
    line = db.get(ProductLine, line_id)
    if line is None:
        raise BusinessError("NOT_FOUND", "产品线不存在", 404)

    product_count = db.scalar(
        select(func.count(Product.id)).where(Product.line_id == line_id)
    ) or 0
    if product_count:
        raise BusinessError(
            "DELETE_BLOCKED", f"该产品线下还有 {product_count} 个产品，请先迁移后再试", 409
        )

    db.delete(line)
    db.commit()
    return SuccessResponse()
```

- [ ] **Step 5: 注册路由**

```python
# backend/app/main.py
from app.api import admin, admin_faults, admin_product_lines, admin_tickets, auth, health, public, stats
...
app.include_router(admin_product_lines.router, prefix="/api/admin", tags=["后台"])
```

同时更新 `backend/app/api/__init__.py` 的 `__all__`。

- [ ] **Step 6: 产品 schema 改为 line_id**

```python
# backend/app/schemas/product.py
class ProductPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    model: str
    line_id: int
    line_name: str | None = None
    sort_order: int


class ProductAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    model: str
    line_id: int
    line_name: str | None = None
    description: str = ""
    is_active: bool
    sort_order: int
    fault_count: int = 0
    created_at: AppDateTime
    updated_at: AppDateTime


class ProductCreate(BaseModel):
    name: str = Field(max_length=100, examples=["智能扫地机器人"])
    model: str = Field(max_length=50, examples=["X1"])
    line_id: int
    description: str | None = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("name", "model")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("名称与型号不能为空")
        return value


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=50)
    line_id: int | None = None
    description: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("name", "model")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("名称与型号不能为空")
        return value
```

- [ ] **Step 7: 改造产品接口**

`backend/app/api/admin.py`：

```python
from sqlalchemy.orm import Session, selectinload
from app.core.permissions import PRODUCT_READ, PRODUCT_WRITE, PART_READ, PART_WRITE, UPLOAD_WRITE, require
from app.models import Fault, Part, Product, ProductLine, User

_PRODUCT_NOT_NULL = ("name", "model", "line_id", "is_active", "sort_order")


def _ensure_line(db: Session, line_id: int, *, allow_inactive: bool = False) -> None:
    line = db.get(ProductLine, line_id)
    if line is None:
        raise BusinessError("NOT_FOUND", "产品线不存在", 404)
    if not line.is_active and not allow_inactive:
        raise BusinessError("LINE_INACTIVE", "产品线已停用，不能用于产品", 400)


def _to_product_admin(product: Product, fault_count: int) -> ProductAdmin:
    return ProductAdmin(
        id=product.id,
        name=product.name,
        model=product.model,
        line_id=product.line_id,
        line_name=product.line_name,
        description=product.description or "",
        is_active=product.is_active,
        sort_order=product.sort_order,
        fault_count=fault_count,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
```

`list_products` 的查询改为：

```python
    stmt = select(Product, fault_count.label("fault_count")).options(selectinload(Product.line))
```

`create_product` 在写入前调用 `_ensure_line(db, payload.line_id)`；`update_product` 在 `data` 含 `line_id` 时调用 `_ensure_line`（允许同一条已停用线保持不变：仅在 `data["line_id"] != product.line_id` 时校验启用状态）。

`public.py` 的产品列表加 `options(selectinload(Product.line))`。

- [ ] **Step 8: 更新产品测试**

`backend/tests/test_products.py` 中所有 `category` 改为 `line_id`；每个用例先建产品线：

```python
def make_line(db, name: str = "扫地机") -> int:
    from app.models import ProductLine

    line = ProductLine(name=name)
    db.add(line)
    db.commit()
    db.refresh(line)
    return line.id
```

创建产品的请求体加 `"line_id": make_line(db)`；响应断言改为 `"line_name"`；公共产品接口的键集合断言改为 `{"id", "name", "model", "line_id", "line_name", "sort_order"}`。

- [ ] **Step 9: 全局测试夹具补 line_id（否则除产品外的测试全部红）**

`Product.line_id` 变成 NOT NULL 后，另外 5 个测试文件里的造数助手也会失败。先把产品线助手放进 `backend/tests/conftest.py`：

```python
from sqlalchemy import select

from app.models import ProductLine, User


def make_line(db: Session, name: str = "测试产品线") -> ProductLine:
    line = db.scalar(select(ProductLine).where(ProductLine.name == name))
    if line is None:
        line = ProductLine(name=name)
        db.add(line)
        db.commit()
        db.refresh(line)
    return line
```

逐个改造数助手（只列改动部分，其余保持原样）：

```python
# backend/tests/test_faults.py
from tests.conftest import auth_headers, login, make_line, make_user

def make_product(db, name: str = "智能扫地机器人", model: str = "X1") -> Product:
    product = Product(name=name, model=model, line_id=make_line(db).id)
    ...

# backend/tests/test_tickets.py
from tests.conftest import auth_headers, login, make_line, make_user

def make_product(db, name: str = "智能扫地机器人", model: str = "X1") -> Product:
    product = Product(name=name, model=model, line_id=make_line(db).id)
    ...

# backend/tests/test_security.py
from tests.conftest import admin_headers, auth_headers, login, make_line, make_user

def make_product(db, name: str = "智能扫地机器人", model: str = "X1") -> Product:
    product = Product(name=name, model=model, line_id=make_line(db).id, is_active=True, sort_order=0)
    ...

# backend/tests/test_stats.py
def make_product_part(db, model: str = "X1"):
    product = Product(name="智能扫地机器人", model=model, line_id=make_line(db).id)
    ...

# backend/tests/test_upload.py
    product = Product(name="扫地机", model="X1", line_id=make_line(db).id, is_active=True, sort_order=0)
```

`test_products.py` 里的局部 `make_line` 可以删除，改用 conftest 的同名函数。

- [ ] **Step 10: 跑全量后端测试**

Run: `pytest -q`
Expected: 全部 PASS

- [ ] **Step 11: 提交**

```bash
git add backend/app/api backend/app/schemas backend/app/main.py backend/tests
git commit -m "feat(product): 产品线 CRUD，产品改为必选产品线并移除 category"
```

---

## Task 7: 工单数据范围

**Files:**
- Create: `backend/app/services/ticket_scope.py`
- Modify: `backend/app/api/admin_tickets.py`
- Test: `backend/tests/test_ticket_scope.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ticket_scope.py
from datetime import datetime, timedelta, timezone

from app.models import Product, ProductLine, Ticket, UserProductLine
from tests.conftest import auth_headers, login, make_user


def _setup(db):
    line_a = ProductLine(name="扫地机")
    line_b = ProductLine(name="净化器")
    db.add_all([line_a, line_b])
    db.flush()
    p_a = Product(line_id=line_a.id, name="扫地机A", model="A1")
    p_b = Product(line_id=line_b.id, name="净化器B", model="B1")
    db.add_all([p_a, p_b])
    db.flush()
    tickets = [
        Ticket(ticket_no="TK202610220001", product_id=p_a.id, contact="13800000001", description="A"),
        Ticket(ticket_no="TK202610220002", product_id=p_b.id, contact="13800000002", description="B"),
        Ticket(ticket_no="TK202610220003", product_id=None, contact="13800000003", description="C"),
    ]
    db.add_all(tickets)
    db.commit()
    return line_a, line_b, tickets


def test_agent_only_sees_own_line(client, db):
    line_a, line_b, tickets = _setup(db)
    agent = make_user(db, username="agent1", role="agent")
    db.add(UserProductLine(user_id=agent.id, line_id=line_a.id))
    db.commit()
    headers = auth_headers(login(client, "agent1")["access_token"])

    body = client.get("/api/admin/tickets", headers=headers).json()

    assert body["total"] == 1
    assert body["items"][0]["ticket_no"] == "TK202610220001"
    assert client.get(f"/api/admin/tickets/{tickets[1].id}", headers=headers).status_code == 403
    assert client.get(f"/api/admin/tickets/{tickets[2].id}", headers=headers).status_code == 403


def test_agent_without_lines_sees_nothing(client, db):
    _setup(db)
    make_user(db, username="agent1", role="agent")
    headers = auth_headers(login(client, "agent1")["access_token"])

    assert client.get("/api/admin/tickets", headers=headers).json()["total"] == 0


def test_expired_line_assignment_hides_tickets(client, db):
    line_a, _, _ = _setup(db)
    agent = make_user(db, username="agent1", role="agent")
    db.add(
        UserProductLine(
            user_id=agent.id,
            line_id=line_a.id,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    db.commit()
    headers = auth_headers(login(client, "agent1")["access_token"])

    assert client.get("/api/admin/tickets", headers=headers).json()["total"] == 0


def test_supervisor_sees_all(client, db):
    _setup(db)
    make_user(db, username="boss", role="supervisor")
    headers = auth_headers(login(client, "boss")["access_token"])

    assert client.get("/api/admin/tickets", headers=headers).json()["total"] == 3
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest backend/tests/test_ticket_scope.py -v`
Expected: FAIL，客服能看到全部工单

- [ ] **Step 3: 实现范围计算**

```python
# backend/app/services/ticket_scope.py
"""工单可见范围。数据范围只作用于工单，知识库对外公开不限制。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.permissions import ALL, data_scope
from app.models import Product, Ticket, User, UserProductLine


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def visible_product_ids(db: Session, user: User) -> set[int] | None:
    """None 表示不受限；空集合表示一条也看不到。"""
    if data_scope(user) == ALL:
        return None

    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(UserProductLine.line_id, UserProductLine.expires_at).where(
            UserProductLine.user_id == user.id
        )
    ).all()
    line_ids = [
        line_id
        for line_id, expires_at in rows
        if expires_at is None or _as_utc(expires_at) > now
    ]
    if not line_ids:
        return set()

    return set(
        db.scalars(select(Product.id).where(Product.line_id.in_(line_ids))).all()
    )


def apply_ticket_scope(stmt, db: Session, user: User):
    product_ids = visible_product_ids(db, user)
    if product_ids is None:
        return stmt
    return stmt.where(Ticket.product_id.in_(product_ids))


def ensure_ticket_visible(db: Session, user: User, ticket: Ticket) -> None:
    product_ids = visible_product_ids(db, user)
    if product_ids is None:
        return
    if ticket.product_id is None or ticket.product_id not in product_ids:
        raise BusinessError("PERMISSION_DENIED", "无权查看该工单", 403)
```

- [ ] **Step 4: 接入工单接口**

`admin_tickets.py`：

```python
from app.core.permissions import TICKET_READ, TICKET_WRITE, require
from app.services.ticket_scope import apply_ticket_scope, ensure_ticket_visible

# list_tickets：
#   1) 参数 `_: User = Depends(get_current_user)` 改为 `user: User = Depends(require(TICKET_READ))`
#   2) 在 `stmt = stmt.order_by(Ticket.created_at.desc(), Ticket.id.desc())` 之前插入：
    stmt = apply_ticket_scope(stmt, db, user)

# get_ticket：
#   1) 参数改为 `user: User = Depends(require(TICKET_READ))`
#   2) 在 `ticket is None` 判断之后插入：
    ensure_ticket_visible(db, user, ticket)

# update_ticket：
#   1) 参数改为 `user: User = Depends(require(TICKET_WRITE))`
#   2) 在 `ticket is None` 判断之后插入：
    ensure_ticket_visible(db, user, ticket)
```

- [ ] **Step 5: 运行测试**

Run: `pytest backend/tests/test_ticket_scope.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/ticket_scope.py backend/app/api/admin_tickets.py \
  backend/tests/test_ticket_scope.py
git commit -m "feat(ticket): 客服按产品线限制工单可见范围"
```

---

## Task 8: 用户管理接口

**Files:**
- Create: `backend/app/schemas/user.py`
- Create: `backend/app/api/admin_users.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_admin_users.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_admin_users.py
from app.core.security import BCRYPT_MAX_BYTES  # noqa: F401
from tests.conftest import auth_headers, login, make_user


def _headers(client, db, role="super_admin"):
    make_user(db, username=f"u_{role}", role=role)
    return auth_headers(login(client, f"u_{role}")["access_token"])


def test_create_list_update_user(client, db):
    headers = _headers(client, db)

    created = client.post(
        "/api/admin/users",
        json={
            "username": "wangwei",
            "real_name": "王伟",
            "password": "Init@12345",
            "role": "agent",
            "product_lines": [],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    listed = client.get("/api/admin/users", headers=headers).json()
    assert any(item["username"] == "wangwei" for item in listed["items"])

    updated = client.put(
        f"/api/admin/users/{user_id}",
        json={"real_name": "王伟伟", "role": "supervisor"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "supervisor"


def test_duplicate_username(client, db):
    headers = _headers(client, db)
    payload = {
        "username": "wangwei", "real_name": "王伟", "password": "Init@12345",
        "role": "agent", "product_lines": [],
    }
    client.post("/api/admin/users", json=payload, headers=headers)

    response = client.post("/api/admin/users", json=payload, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "USERNAME_DUPLICATED"


def test_cannot_disable_or_demote_self(client, db):
    make_user(db, username="boss")
    headers = auth_headers(login(client, "boss")["access_token"])
    me = client.get("/api/auth/me", headers=headers).json()["user"]

    assert client.put(
        f"/api/admin/users/{me['id']}", json={"is_active": False}, headers=headers
    ).status_code == 400
    assert client.put(
        f"/api/admin/users/{me['id']}", json={"role": "agent"}, headers=headers
    ).status_code == 400


def test_last_super_admin_guard_rejects_when_none_left(db):
    """守卫本身：目标之外没有其他在用超管时必须拒绝。

    通过 API 很难构造（操作者本身也是超管，改自己会被前面的规则拦住），
    所以直接测守卫函数。
    """
    from app.api.admin_users import _ensure_other_super_admin
    from app.core.exceptions import BusinessError

    only = make_user(db, username="boss")

    try:
        _ensure_other_super_admin(db, only.id)
    except BusinessError as exc:
        assert exc.code == "LAST_SUPER_ADMIN"
    else:
        raise AssertionError("应当拒绝")


def test_reset_password_returns_once_and_works(client, db):
    headers = _headers(client, db)
    created = client.post(
        "/api/admin/users",
        json={"username": "wangwei", "real_name": "王伟", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    ).json()

    body = client.post(f"/api/admin/users/{created['id']}/reset-password", headers=headers).json()

    assert len(body["password"]) == 12
    assert login(client, "wangwei", body["password"])["user"]["username"] == "wangwei"


def test_auditor_cannot_create_user(client, db):
    headers = _headers(client, db, role="auditor")

    response = client.post(
        "/api/admin/users",
        json={"username": "x", "real_name": "x", "password": "Init@12345",
              "role": "agent", "product_lines": []},
        headers=headers,
    )

    assert response.status_code == 403
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest backend/tests/test_admin_users.py -v`
Expected: FAIL，404（接口不存在）

- [ ] **Step 3: 新建用户 schema**

```python
# backend/app/schemas/user.py
"""用户管理与临时授权的请求/响应。"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES
from app.schemas.common import AppDateTime

ROLE_VALUES = ("super_admin", "supervisor", "agent", "auditor")


def _validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("密码至少 8 位")
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"密码不能超过 {BCRYPT_MAX_BYTES} 字节")
    return value


class ProductLineAssignment(BaseModel):
    line_id: int
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def _future_or_none(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value <= datetime.now(timezone.utc):
            raise ValueError("到期时间必须晚于当前时间")
        return value


class ProductLineBrief(BaseModel):
    id: int
    name: str
    expires_at: AppDateTime | None = None


class UserCreate(BaseModel):
    username: str = Field(max_length=50)
    real_name: str = Field(max_length=50)
    password: str
    role: str = "agent"
    product_lines: list[ProductLineAssignment] = Field(default_factory=list)

    @field_validator("username", "real_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("password")
    @classmethod
    def _password_rules(cls, value: str) -> str:
        return _validate_password(value)

    @field_validator("role")
    @classmethod
    def _role_rules(cls, value: str) -> str:
        if value not in ROLE_VALUES:
            raise ValueError("角色不合法")
        return value


class UserUpdate(BaseModel):
    real_name: str | None = Field(default=None, max_length=50)
    role: str | None = None
    is_active: bool | None = None

    @field_validator("real_name")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("姓名不能为空")
        return value

    @field_validator("role")
    @classmethod
    def _role_rules(cls, value: str | None) -> str | None:
        if value is not None and value not in ROLE_VALUES:
            raise ValueError("角色不合法")
        return value


class UserListItem(BaseModel):
    id: int
    username: str
    real_name: str
    role: str
    is_active: bool
    last_login_at: AppDateTime | None = None
    created_at: AppDateTime
    product_lines: list[ProductLineBrief] = Field(default_factory=list)


class UserPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[UserListItem]


class ResetPasswordResponse(BaseModel):
    password: str
```

- [ ] **Step 4: 新建用户路由（本任务只做用户 CRUD 与重置密码）**

```python
# backend/app/api/admin_users.py
"""用户管理。临时授权与候选人接口在后续任务追加。"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import BusinessError
from app.core.permissions import USER_READ, USER_WRITE, effective_permissions, require
from app.core.security import hash_password
from app.database import get_db
from app.models import ProductLine, User, UserProductLine
from app.schemas.common import ErrorBody
from app.schemas.user import (
    ProductLineAssignment,
    ProductLineBrief,
    ResetPasswordResponse,
    UserCreate,
    UserListItem,
    UserPage,
    UserUpdate,
)
from app.utils.search import LIKE_ESCAPE, like_pattern

router = APIRouter()

_PASSWORD_ALPHABET = "".join(
    c for c in string.ascii_letters + string.digits if c not in "0O1lI"
)


def _gen_password(length: int = 12) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def _to_item(user: User) -> UserListItem:
    return UserListItem(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        role=user.role,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        product_lines=[
            ProductLineBrief(
                id=assignment.line.id,
                name=assignment.line.name,
                expires_at=assignment.expires_at,
            )
            for assignment in user.product_lines
        ],
    )


def _ensure_lines_exist(db: Session, assignments: list[ProductLineAssignment]) -> None:
    ids = {item.line_id for item in assignments}
    if not ids:
        return
    found = set(db.scalars(select(ProductLine.id).where(ProductLine.id.in_(ids))).all())
    missing = ids - found
    if missing:
        raise BusinessError("NOT_FOUND", f"产品线不存在：{sorted(missing)}", 404)


def _replace_lines(db: Session, user: User, assignments: list[ProductLineAssignment]) -> None:
    _ensure_lines_exist(db, assignments)
    db.execute(
        UserProductLine.__table__.delete().where(UserProductLine.user_id == user.id)
    )
    db.add_all(
        [
            UserProductLine(
                user_id=user.id, line_id=item.line_id, expires_at=item.expires_at
            )
            for item in assignments
        ]
    )


def _ensure_other_super_admin(db: Session, user_id: int) -> None:
    others = db.scalars(
        select(User.id)
        .where(
            User.role == "super_admin",
            User.is_active.is_(True),
            User.id != user_id,
        )
        .with_for_update()
    ).all()
    if not others:
        raise BusinessError("LAST_SUPER_ADMIN", "系统至少需要保留一个在用超级管理员", 400)


@router.get("/users", response_model=UserPage, summary="用户列表")
def list_users(
    keyword: str | None = Query(None, max_length=100),
    role: str | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_READ)),
) -> UserPage:
    stmt = select(User).options(
        selectinload(User.product_lines).selectinload(UserProductLine.line)
    )
    conditions = []
    if role:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))
    if keyword and keyword.strip():
        pattern = like_pattern(keyword.strip().lower())
        conditions.append(
            or_(
                func.lower(User.username).like(pattern, escape=LIKE_ESCAPE),
                func.lower(User.real_name).like(pattern, escape=LIKE_ESCAPE),
            )
        )

    total = db.scalar(select(func.count(User.id)).where(*conditions)) or 0
    stmt = (
        stmt.where(*conditions)
        .order_by(User.is_active.desc(), User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return UserPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_item(user) for user in db.scalars(stmt)],
    )


@router.post(
    "/users",
    status_code=201,
    response_model=UserListItem,
    summary="新建用户",
    responses={409: {"model": ErrorBody, "description": "用户名重复"}},
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_WRITE)),
) -> UserListItem:
    _ensure_lines_exist(db, payload.product_lines)
    user = User(
        username=payload.username,
        real_name=payload.real_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.flush()
        _replace_lines(db, user, payload.product_lines)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError(
            "USERNAME_DUPLICATED", f"用户名 {payload.username} 已存在", 409
        ) from exc
    db.refresh(user)
    user = db.scalar(
        select(User)
        .options(selectinload(User.product_lines).selectinload(UserProductLine.line))
        .where(User.id == user.id)
    )
    return _to_item(user)


@router.put("/users/{user_id}", response_model=UserListItem, summary="修改用户")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require(USER_WRITE)),
) -> UserListItem:
    user = db.get(User, user_id)
    if user is None:
        raise BusinessError("NOT_FOUND", "用户不存在", 404)

    data = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    if user_id == actor.id:
        if "is_active" in data and data["is_active"] is False:
            raise BusinessError("SELF_DISABLE", "不能停用自己", 400)
        if "role" in data and data["role"] != actor.role:
            raise BusinessError("SELF_ROLE_CHANGE", "不能修改自己的角色", 400)

    demoting = data.get("role") not in (None, "super_admin") and user.role == "super_admin"
    disabling = data.get("is_active") is False and user.is_active and user.role == "super_admin"
    if (demoting or disabling) and user.is_active:
        _ensure_other_super_admin(db, user.id)

    for field, value in data.items():
        setattr(user, field, value)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    user = db.scalar(
        select(User)
        .options(selectinload(User.product_lines).selectinload(UserProductLine.line))
        .where(User.id == user.id)
    )
    return _to_item(user)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=ResetPasswordResponse,
    summary="重置密码（一次性返回明文）",
)
def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_WRITE)),
) -> ResetPasswordResponse:
    user = db.get(User, user_id)
    if user is None:
        raise BusinessError("NOT_FOUND", "用户不存在", 404)

    password = _gen_password()
    user.password_hash = hash_password(password)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    return ResetPasswordResponse(password=password)
```

- [ ] **Step 5: 注册路由**

`backend/app/main.py` 增加：

```python
from app.api import ..., admin_users
app.include_router(admin_users.router, prefix="/api/admin", tags=["后台"])
```

同步更新 `backend/app/api/__init__.py`。

- [ ] **Step 6: 运行测试**

Run: `pytest backend/tests/test_admin_users.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/schemas/user.py backend/app/api/admin_users.py \
  backend/app/main.py backend/app/api/__init__.py backend/tests/test_admin_users.py
git commit -m "feat(user): 用户列表、新建、修改与重置密码接口"
```

---

## Task 9: 临时授权与产品线分配接口

**Files:**
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/api/admin_users.py`
- Test: `backend/tests/test_grants.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_grants.py
from datetime import datetime, timedelta, timezone

from app.core.permissions import effective_permissions
from tests.conftest import auth_headers, login, make_user


def _admin_headers(client, db):
    make_user(db, username="boss")
    return auth_headers(login(client, "boss")["access_token"])


def _make_agent(db):
    return make_user(db, username="agent1", role="agent")


def test_grant_adds_permission_with_closure(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    response = client.post(
        f"/api/admin/users/{agent.id}/grants",
        json={"permission": "fault:write", "expires_at": expires, "reason": "临时接手知识库"},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    perms = effective_permissions(db, agent)
    assert {"fault:write", "fault:read", "product:read", "part:read", "upload:write"} <= perms


def test_grant_user_write_rejected(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    response = client.post(
        f"/api/admin/users/{agent.id}/grants",
        json={"permission": "user:write", "expires_at": expires, "reason": "提权"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PERMISSION"


def test_grant_past_expiry_rejected(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)

    response = client.post(
        f"/api/admin/users/{agent.id}/grants",
        json={
            "permission": "stats:read",
            "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            "reason": "过期",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_revoke_grant(client, db):
    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    grant = client.post(
        f"/api/admin/users/{agent.id}/grants",
        json={
            "permission": "stats:read",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "reason": "临时",
        },
        headers=headers,
    ).json()

    assert client.delete(
        f"/api/admin/users/{agent.id}/grants/{grant['id']}", headers=headers
    ).status_code == 200
    assert "stats:read" not in effective_permissions(db, agent)


def test_replace_product_lines(client, db):
    from app.models import ProductLine

    headers = _admin_headers(client, db)
    agent = _make_agent(db)
    line = ProductLine(name="扫地机")
    db.add(line)
    db.commit()

    response = client.put(
        f"/api/admin/users/{agent.id}/product-lines",
        json=[{"line_id": line.id, "expires_at": None}],
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["product_lines"][0]["name"] == "扫地机"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest backend/tests/test_grants.py -v`
Expected: FAIL，404（接口不存在）

- [ ] **Step 3: 扩展 schema**

```python
# backend/app/schemas/user.py 追加
class GrantCreate(BaseModel):
    permission: str
    expires_at: datetime
    reason: str = Field(min_length=1, max_length=200)

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请填写授权事由")
        return value

    @field_validator("expires_at")
    @classmethod
    def _future_within_limit(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if value <= now:
            raise ValueError("到期时间必须晚于当前时间")
        if value > now + timedelta(days=180):
            raise ValueError("临时授权最长 180 天")
        return value


class GrantOut(BaseModel):
    id: int
    permission: str
    expires_at: AppDateTime
    reason: str
    granted_by_name: str | None = None
    granted_at: AppDateTime
    revoked_at: AppDateTime | None = None
    is_active: bool
```

在文件顶部补 `from datetime import timedelta`。

- [ ] **Step 4: 扩展用户路由**

```python
# backend/app/api/admin_users.py 追加
from app.core.permissions import grantable_permissions
from app.models import UserPermissionGrant
from app.schemas.user import GrantCreate, GrantOut

@router.get("/users/{user_id}/grants", response_model=list[GrantOut], summary="临时授权列表")
def list_grants(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_READ)),
) -> list[GrantOut]:
    if db.get(User, user_id) is None:
        raise BusinessError("NOT_FOUND", "用户不存在", 404)
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(UserPermissionGrant, User.real_name)
        .outerjoin(User, UserPermissionGrant.granted_by == User.id)
        .where(UserPermissionGrant.user_id == user_id)
        .order_by(UserPermissionGrant.granted_at.desc(), UserPermissionGrant.id.desc())
    ).all()
    return [
        GrantOut(
            id=grant.id,
            permission=grant.permission,
            expires_at=grant.expires_at,
            reason=grant.reason,
            granted_by_name=granted_by_name,
            granted_at=grant.granted_at,
            revoked_at=grant.revoked_at,
            is_active=grant.revoked_at is None
            and (grant.expires_at if grant.expires_at.tzinfo else grant.expires_at.replace(tzinfo=timezone.utc)) > now,
        )
        for grant, granted_by_name in rows
    ]


@router.post(
    "/users/{user_id}/grants",
    status_code=201,
    response_model=GrantOut,
    summary="发放临时授权",
)
def create_grant(
    user_id: int,
    payload: GrantCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require(USER_WRITE)),
) -> GrantOut:
    target = db.get(User, user_id)
    if target is None:
        raise BusinessError("NOT_FOUND", "用户不存在", 404)
    if not target.is_active:
        raise BusinessError("USER_DISABLED", "账号已停用，不能发放临时授权", 400)
    if payload.permission not in grantable_permissions():
        raise BusinessError("INVALID_PERMISSION", "该权限不可临时授予", 400)
    if payload.permission not in effective_permissions(db, actor):
        raise BusinessError("INVALID_PERMISSION", "不能授予自己不具备的权限", 400)

    grant = UserPermissionGrant(
        user_id=user_id,
        permission=payload.permission,
        expires_at=payload.expires_at,
        reason=payload.reason.strip(),
        granted_by=actor.id,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return GrantOut(
        id=grant.id,
        permission=grant.permission,
        expires_at=grant.expires_at,
        reason=grant.reason,
        granted_by_name=actor.real_name,
        granted_at=grant.granted_at,
        revoked_at=None,
        is_active=True,
    )


@router.delete(
    "/users/{user_id}/grants/{grant_id}",
    response_model=SuccessResponse,
    summary="提前收回临时授权",
)
def revoke_grant(
    user_id: int,
    grant_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_WRITE)),
) -> SuccessResponse:
    grant = db.get(UserPermissionGrant, grant_id)
    if grant is None or grant.user_id != user_id:
        raise BusinessError("NOT_FOUND", "临时授权不存在", 404)
    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return SuccessResponse()


@router.put(
    "/users/{user_id}/product-lines",
    response_model=UserListItem,
    summary="整体替换产品线授权",
)
def replace_product_lines(
    user_id: int,
    assignments: list[ProductLineAssignment],
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_WRITE)),
) -> UserListItem:
    user = db.get(User, user_id)
    if user is None:
        raise BusinessError("NOT_FOUND", "用户不存在", 404)

    _replace_lines(db, user, assignments)
    db.commit()
    user = db.scalar(
        select(User)
        .options(selectinload(User.product_lines).selectinload(UserProductLine.line))
        .where(User.id == user_id)
    )
    return _to_item(user)
```

`SuccessResponse` 需在 `admin_users.py` 顶部导入。

- [ ] **Step 5: 运行测试**

Run: `pytest backend/tests/test_grants.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/user.py backend/app/api/admin_users.py backend/tests/test_grants.py
git commit -m "feat(authz): 临时授权发放/收回与产品线分配接口"
```

---

## Task 10: 工单改派与候选人接口

**Files:**
- Modify: `backend/app/services/ticket_scope.py`
- Modify: `backend/app/api/admin_users.py`
- Modify: `backend/app/api/admin_tickets.py`
- Modify: `backend/app/schemas/user.py`
- Test: `backend/tests/test_ticket_assign.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ticket_assign.py
from app.models import Product, ProductLine, Ticket, UserProductLine
from tests.conftest import auth_headers, login, make_user


def _setup(db):
    line_a = ProductLine(name="扫地机")
    line_b = ProductLine(name="净化器")
    db.add_all([line_a, line_b])
    db.flush()
    product = Product(line_id=line_a.id, name="扫地机A", model="A1")
    other = Product(line_id=line_b.id, name="净化器B", model="B1")
    db.add_all([product, other])
    db.flush()
    ticket = Ticket(ticket_no="TK202610220001", product_id=product.id, contact="138", description="x")
    db.add(ticket)
    db.commit()
    return line_a, line_b, product, ticket


def test_assignable_filters_by_line(client, db):
    line_a, line_b, product, _ = _setup(db)
    make_user(db, username="boss", real_name="主管", role="supervisor")
    agent_a = make_user(db, username="agent_a", real_name="客服A", role="agent")
    agent_b = make_user(db, username="agent_b", real_name="客服B", role="agent")
    db.add_all(
        [
            UserProductLine(user_id=agent_a.id, line_id=line_a.id),
            UserProductLine(user_id=agent_b.id, line_id=line_b.id),
        ]
    )
    db.commit()
    headers = auth_headers(login(client, "boss")["access_token"])

    body = client.get(
        "/api/admin/users/assignable", params={"product_id": product.id}, headers=headers
    ).json()

    names = {item["real_name"] for item in body}
    assert "主管" in names  # 主管是 ALL 范围
    assert "客服A" in names
    assert "客服B" not in names


def test_agent_cannot_assign(client, db):
    _, _, _, ticket = _setup(db)
    make_user(db, username="agent1", role="agent")
    headers = auth_headers(login(client, "agent1")["access_token"])

    response = client.put(
        f"/api/admin/tickets/{ticket.id}", json={"assignee_id": 1}, headers=headers
    )

    assert response.status_code == 403


def test_supervisor_can_assign_same_line_agent(client, db):
    line_a, _, _, ticket = _setup(db)
    make_user(db, username="boss", real_name="主管", role="supervisor")
    agent = make_user(db, username="agent1", real_name="客服A", role="agent")
    db.add(UserProductLine(user_id=agent.id, line_id=line_a.id))
    db.commit()
    headers = auth_headers(login(client, "boss")["access_token"])

    response = client.put(
        f"/api/admin/tickets/{ticket.id}", json={"assignee_id": agent.id}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["assignee_id"] == agent.id


def test_supervisor_cannot_assign_cross_line_agent(client, db):
    _, line_b, _, ticket = _setup(db)
    make_user(db, username="boss", real_name="主管", role="supervisor")
    agent = make_user(db, username="agent1", real_name="客服B", role="agent")
    db.add(UserProductLine(user_id=agent.id, line_id=line_b.id))
    db.commit()
    headers = auth_headers(login(client, "boss")["access_token"])

    response = client.put(
        f"/api/admin/tickets/{ticket.id}", json={"assignee_id": agent.id}, headers=headers
    )

    assert response.status_code == 400
    assert response.json()["code"] == "ASSIGNEE_OUT_OF_SCOPE"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest backend/tests/test_ticket_assign.py -v`
Expected: FAIL，agent 改派返回 200 或 404

- [ ] **Step 3: 扩展范围服务**

```python
# backend/app/services/ticket_scope.py 追加
from app.core.permissions import TICKET_WRITE, effective_permissions, grantable_permissions


def assignable_users(db: Session, product_id: int | None) -> list[User]:
    candidates = db.scalars(
        select(User).where(User.is_active.is_(True)).order_by(User.real_name, User.id)
    ).all()
    result: list[User] = []
    for user in candidates:
        if TICKET_WRITE not in effective_permissions(db, user):
            continue
        product_ids = visible_product_ids(db, user)
        if product_ids is None:
            result.append(user)
        elif product_id is not None and product_id in product_ids:
            result.append(user)
    return result


def ensure_assignable(db: Session, ticket: Ticket, assignee_id: int) -> User:
    assignee = db.get(User, assignee_id)
    if assignee is None:
        raise BusinessError("NOT_FOUND", "处理人不存在", 404)
    if not assignee.is_active:
        raise BusinessError("ASSIGNEE_DISABLED", "该账号已停用，不能作为处理人", 400)
    if TICKET_WRITE not in effective_permissions(db, assignee):
        raise BusinessError("ASSIGNEE_NO_PERMISSION", "该账号没有处理工单的权限", 400)

    product_ids = visible_product_ids(db, assignee)
    if product_ids is not None:
        if ticket.product_id is None or ticket.product_id not in product_ids:
            raise BusinessError("ASSIGNEE_OUT_OF_SCOPE", "该账号看不到此工单所属产品线", 400)
    return assignee
```

- [ ] **Step 4: 候选人接口与 schema**

```python
# backend/app/schemas/user.py 追加
class AssignableUser(BaseModel):
    id: int
    real_name: str
```

```python
# backend/app/api/admin_users.py 追加
from app.core.permissions import TICKET_ASSIGN
from app.schemas.user import AssignableUser
from app.services.ticket_scope import assignable_users

@router.get(
    "/users/assignable",
    response_model=list[AssignableUser],
    summary="可改派的处理人",
)
def list_assignable(
    product_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require(TICKET_ASSIGN)),
) -> list[AssignableUser]:
    return [
        AssignableUser(id=user.id, real_name=user.real_name)
        for user in assignable_users(db, product_id)
    ]
```

- [ ] **Step 5: 工单更新校验改派**

```python
# backend/app/api/admin_tickets.py
from app.core.permissions import TICKET_ASSIGN, TICKET_WRITE, effective_permissions, require
from app.services.ticket_scope import ensure_assignable, ensure_ticket_visible

def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require(TICKET_WRITE)),
) -> TicketDetail:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise BusinessError("NOT_FOUND", "工单不存在", 404)
    ensure_ticket_visible(db, user, ticket)

    data = payload.model_dump(exclude_unset=True)
    if "assignee_id" in data:
        if TICKET_ASSIGN not in effective_permissions(db, user):
            raise BusinessError("PERMISSION_DENIED", "无权限改派工单", 403)
        if data["assignee_id"] is not None:
            ensure_assignable(db, ticket, data["assignee_id"])

    apply_update(db, ticket, payload, user)
    return _detail(db, ticket)
```

移除原来只校验"用户存在"的分支。

- [ ] **Step 6: 运行测试**

Run: `pytest backend/tests/test_ticket_assign.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/ticket_scope.py backend/app/api/admin_users.py \
  backend/app/api/admin_tickets.py backend/app/schemas/user.py \
  backend/tests/test_ticket_assign.py
git commit -m "feat(ticket): 改派权限与候选人可见性校验"
```

---

## Task 11: 前端权限基础设施

**Files:**
- Create: `frontend/src/utils/permissions.js`
- Create: `frontend/src/utils/permissions.spec.js`
- Modify: `frontend/src/api/auth.js`
- Modify: `frontend/src/api/request.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/views/admin/Login.vue`
- Modify: `frontend/src/views/admin/Layout.vue`
- Modify: `frontend/src/views/admin/Layout.spec.js`

- [ ] **Step 1: 写失败测试**

```javascript
// frontend/src/utils/permissions.spec.js
import { beforeEach, describe, expect, it } from 'vitest'
import { hasPermission, loadPermissions, setPermissions } from './permissions'

beforeEach(() => localStorage.clear())

describe('permissions', () => {
  it('默认没有任何权限', () => {
    expect(loadPermissions()).toEqual([])
    expect(hasPermission('ticket:read')).toBe(false)
  })

  it('写入后按权限码判断，去重', () => {
    setPermissions(['ticket:read', 'ticket:read', 'stats:read'])
    expect(loadPermissions()).toEqual(['ticket:read', 'stats:read'])
    expect(hasPermission('ticket:read')).toBe(true)
    expect(hasPermission('user:write')).toBe(false)
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test -- src/utils/permissions.spec.js`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现权限工具**

```javascript
// frontend/src/utils/permissions.js
import { ref } from 'vue'

const STORAGE_KEY = 'permissions'

export function loadPermissions() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const current = ref(loadPermissions())

export function setPermissions(list) {
  current.value = [...new Set(Array.isArray(list) ? list : [])]
  localStorage.setItem(STORAGE_KEY, JSON.stringify(current.value))
}

export function clearPermissions() {
  current.value = []
  localStorage.removeItem(STORAGE_KEY)
}

export function hasPermission(code) {
  return current.value.includes(code)
}

export const permissions = current
```

- [ ] **Step 4: 运行测试**

Run: `cd frontend && npm test -- src/utils/permissions.spec.js`
Expected: PASS

- [ ] **Step 5: 增加 /auth/me 与清理逻辑**

```javascript
// frontend/src/api/auth.js 追加
export function fetchMe() {
  return request.get('/auth/me')
}
```

`request.js` 的 401/403 清理分支补 `clearPermissions()`：

```javascript
import { clearPermissions } from '../utils/permissions'

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const code = error.response?.data?.code
    if (code === 'AUTH_TOKEN_EXPIRED' || code === 'AUTH_USER_DISABLED') {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      clearPermissions()
      if (!location.pathname.endsWith('/admin/login')) {
        location.href = '/admin/login'
      }
    }
    return Promise.reject(error)
  }
)
```

- [ ] **Step 6: 登录保存权限**

```javascript
// frontend/src/views/admin/Login.vue
import { setPermissions } from '../../utils/permissions'

// onSubmit() 成功分支：
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    setPermissions(data.permissions)
```

- [ ] **Step 7: 路由守卫**

```javascript
// frontend/src/router/index.js
import { fetchMe } from '../api/auth'
import { clearPermissions, hasPermission, setPermissions } from '../utils/permissions'
```

守卫：

```javascript
router.beforeEach(async (to) => {
  if (to.meta.public) return true
  if (!localStorage.getItem('token')) {
    return { path: '/admin/login', query: { redirect: to.fullPath } }
  }

  if (!localStorage.getItem('permissions')) {
    try {
      const data = await fetchMe()
      setPermissions(data.permissions)
    } catch {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      clearPermissions()
      return { path: '/admin/login', query: { redirect: to.fullPath } }
    }
  }

  if (to.meta.permission && !hasPermission(to.meta.permission)) {
    return { path: '/admin/faults' }
  }
  if (to.meta.requires && !to.meta.requires.every(hasPermission)) {
    return { path: '/admin/faults' }
  }
  return true
})
```

- [ ] **Step 8: Layout 菜单与角色标签按权限**

```javascript
// frontend/src/views/admin/Layout.vue
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { fetchMe } from '../../api/auth'
import { hasPermission, setPermissions } from '../../utils/permissions'

const NAV_ITEMS = [
  { path: '/admin/tickets', label: '工单管理', permission: 'ticket:read' },
  { path: '/admin/products', label: '产品管理', permission: 'product:read' },
  { path: '/admin/parts', label: '零件管理', permission: 'part:read' },
  { path: '/admin/faults', label: '故障知识库', permission: 'fault:read' },
  { path: '/admin/stats', label: '数据看板', permission: 'stats:read' }
]
// 用户管理菜单项在 Task 12 建页后追加

const navItems = computed(() => NAV_ITEMS.filter((item) => hasPermission(item.permission)))

const roleLabel = computed(() => {
  const map = {
    super_admin: '超级管理员',
    supervisor: '售后主管',
    agent: '一线客服',
    auditor: '只读审计'
  }
  return map[user.value.role] || ''
})
```

模板侧栏与窄屏下拉都改为 `v-for="item in navItems"`；删除写死的五个 `el-menu-item`。

每次后台路由切换刷新权限：

```javascript
import { watch } from 'vue'
watch(
  () => route.fullPath,
  async () => {
    try {
      const data = await fetchMe()
      setPermissions(data.permissions)
    } catch {
      // 401/403 已由拦截器跳登录；网络错误忽略，避免误退出
    }
  }
)
```

- [ ] **Step 9: 更新 Layout 测试夹具**

`Layout.spec.js` 的 mock 与 localStorage 注入改为：

```javascript
vi.mock('../../api/auth', () => ({
  changePassword: vi.fn(),
  fetchMe: vi.fn().mockResolvedValue({ permissions: ['ticket:read'] })
}))

import { setPermissions } from '../../utils/permissions'

localStorage.setItem(
  'user',
  JSON.stringify({ username: 'admin', real_name: '超级管理员', role: 'super_admin' })
)
setPermissions(['ticket:read'])
```

（`setPermissions` 同时更新内存中的响应式权限集合与 localStorage；只写 localStorage 不会刷新已导入模块里的 `current`。）

- [ ] **Step 10: 运行前端测试与 lint**

Run: `cd frontend && npm test -- src/utils/permissions.spec.js src/views/admin/Layout.spec.js && npm run lint`
Expected: PASS

- [ ] **Step 11: 提交**

```bash
git add frontend/src/utils/permissions.js frontend/src/utils/permissions.spec.js \
  frontend/src/api/auth.js frontend/src/api/request.js frontend/src/router/index.js \
  frontend/src/views/admin/Login.vue frontend/src/views/admin/Layout.vue \
  frontend/src/views/admin/Layout.spec.js
git commit -m "feat(frontend): 菜单与路由按权限码渲染"
```

---

## Task 12: 用户管理页（P-18）

**Files:**
- Create: `frontend/src/views/admin/users/UserList.vue`
- Create: `frontend/src/views/admin/users/UserList.spec.js`
- Modify: `frontend/src/api/admin.js`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: 补 API 封装**

```javascript
// frontend/src/api/admin.js 追加
export function adminListUsers(params) {
  return request.get('/admin/users', { params })
}

export function adminCreateUser(payload) {
  return request.post('/admin/users', payload)
}

export function adminUpdateUser(id, payload) {
  return request.put(`/admin/users/${id}`, payload)
}

export function adminResetPassword(id) {
  return request.post(`/admin/users/${id}/reset-password`)
}

export function adminListGrants(id) {
  return request.get(`/admin/users/${id}/grants`)
}

export function adminCreateGrant(id, payload) {
  return request.post(`/admin/users/${id}/grants`, payload)
}

export function adminRevokeGrant(id, grantId) {
  return request.delete(`/admin/users/${id}/grants/${grantId}`)
}

export function adminReplaceUserLines(id, assignments) {
  return request.put(`/admin/users/${id}/product-lines`, assignments)
}

export function adminListProductLines(params) {
  return request.get('/admin/product-lines', { params })
}

export function adminCreateProductLine(payload) {
  return request.post('/admin/product-lines', payload)
}

export function adminUpdateProductLine(id, payload) {
  return request.put(`/admin/product-lines/${id}`, payload)
}

export function adminDeleteProductLine(id) {
  return request.delete(`/admin/product-lines/${id}`)
}

export function adminListAssignable(params) {
  return request.get('/admin/users/assignable', { params })
}
```

- [ ] **Step 2: 写失败测试**

```javascript
// frontend/src/views/admin/users/UserList.spec.js
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import UserList from './UserList.vue'
import { setPermissions } from '../../../utils/permissions'

vi.mock('../../../api/admin', () => ({
  adminListUsers: vi.fn(),
  adminListProductLines: vi.fn(),
  adminCreateUser: vi.fn(),
  adminUpdateUser: vi.fn(),
  adminResetPassword: vi.fn(),
  adminListGrants: vi.fn(),
  adminCreateGrant: vi.fn(),
  adminRevokeGrant: vi.fn(),
  adminReplaceUserLines: vi.fn()
}))

import { adminListProductLines, adminListUsers } from '../../../api/admin'

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['user:read', 'user:write', 'product_line:read'])
  adminListUsers.mockResolvedValue({ total: 1, page: 1, page_size: 20, items: [
    {
      id: 1, username: 'wangwei', real_name: '王伟', role: 'agent', is_active: true,
      last_login_at: null, created_at: '2026-10-01T09:00:00+08:00',
      product_lines: [{ id: 1, name: '扫地机', expires_at: null }]
    }
  ] })
  adminListProductLines.mockResolvedValue({ items: [] })
})

describe('UserList', () => {
  it('加载并渲染用户、角色与产品线', async () => {
    const wrapper = mount(UserList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    expect(adminListUsers).toHaveBeenCalled()
    expect(wrapper.text()).toContain('wangwei')
    expect(wrapper.text()).toContain('一线客服')
    expect(wrapper.text()).toContain('扫地机')
  })
})
```

- [ ] **Step 3: 运行确认失败**

Run: `cd frontend && npm test -- src/views/admin/users/UserList.spec.js`
Expected: FAIL，组件不存在

- [ ] **Step 4: 实现页面**

完整实现（样式复用 `ProductList.vue` 的 `.page/.head/.head-actions/.pager`）：

```vue
<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>用户管理</span>
          <div class="head-actions">
            <el-input v-model="filters.keyword" placeholder="搜索账号或姓名" clearable class="kw" @input="onKeywordInput" @clear="reload" />
            <el-select v-model="filters.role" placeholder="全部角色" clearable class="role" @change="reload">
              <el-option v-for="item in ROLE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-select v-model="filters.isActive" placeholder="全部状态" clearable class="status" @change="reload">
              <el-option label="启用" :value="true" />
              <el-option label="停用" :value="false" />
            </el-select>
            <el-button v-if="canWrite" type="primary" @click="openCreate">新建用户</el-button>
          </div>
        </div>
      </template>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table v-else v-loading="loading" :data="rows" row-key="id" border>
        <el-table-column label="账号 / 姓名" min-width="180">
          <template #default="{ row }">
            <div class="name">{{ row.username }}</div>
            <div class="sub">{{ row.real_name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="120">
          <template #default="{ row }">{{ roleLabel(row.role) }}</template>
        </el-table-column>
        <el-table-column label="产品线" min-width="180">
          <template #default="{ row }">
            <el-tag v-for="line in row.product_lines" :key="line.id" size="small" class="tag">
              {{ line.name }}{{ line.expires_at ? '（临时）' : '' }}
            </el-tag>
            <span v-if="!row.product_lines.length" class="sub">未分配</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-switch
              v-if="canWrite && row.id !== currentUserId"
              :model-value="row.is_active"
              :loading="togglingId === row.id"
              inline-prompt
              active-text="启用"
              inactive-text="停用"
              @change="(value) => onToggleActive(row, value)"
            />
            <span v-else>{{ row.is_active ? '启用' : '停用' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最近登录" width="140">
          <template #default="{ row }">{{ row.last_login_at ? formatDateTime(row.last_login_at) : '从未登录' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" align="center">
          <template #default="{ row }">
            <el-button v-if="canWrite" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canWrite" link type="warning" @click="onResetPassword(row)">重置密码</el-button>
            <el-button link type="info" @click="openGrants(row)">临时授权</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="!loadError"
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        class="pager"
        layout="total, sizes, prev, pager, next"
        :page-sizes="[10, 20, 50]"
        :total="pagination.total"
        @current-change="load"
        @size-change="onSizeChange"
      />
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑用户' : '新建用户'" width="620px" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="账号" prop="username">
          <el-input v-model="form.username" maxlength="50" :disabled="Boolean(editingId)" />
        </el-form-item>
        <el-form-item label="姓名" prop="real_name">
          <el-input v-model="form.real_name" maxlength="50" />
        </el-form-item>
        <el-form-item v-if="!editingId" label="初始密码" prop="password">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role">
            <el-option v-for="item in ROLE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品线">
          <div class="assignments">
            <div v-for="(item, index) in form.product_lines" :key="index" class="assignment-row">
              <el-select v-model="item.line_id" placeholder="选择产品线" class="line-select">
                <el-option v-for="line in lines" :key="line.id" :label="line.name" :value="line.id" />
              </el-select>
              <el-date-picker v-model="item.expires_at" type="date" placeholder="长期（留空）" class="date" value-format="YYYY-MM-DD" />
              <el-button link type="danger" @click="form.product_lines.splice(index, 1)">删除</el-button>
            </div>
            <el-button link type="primary" @click="addAssignment">添加产品线</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="passwordVisible" title="密码已重置" width="420px">
      <el-alert type="success" :closable="false" title="请立即复制并通过安全渠道交给本人，关闭后无法再次查看" />
      <div class="password">{{ resetPassword }}</div>
      <template #footer>
        <el-button @click="passwordVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="grantsVisible" :title="`临时授权 — ${grantUser?.real_name || ''}`" size="560px" @open="loadGrants">
      <el-table :data="grants" size="small" border>
        <el-table-column prop="permission" label="权限" width="150" />
        <el-table-column prop="reason" label="事由" min-width="120" />
        <el-table-column label="到期" width="130">
          <template #default="{ row }">{{ formatDateTime(row.expires_at) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '生效' : '失效' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canWrite" label="操作" width="80">
          <template #default="{ row }">
            <el-button v-if="row.is_active" link type="danger" @click="onRevoke(row)">收回</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template v-if="canWrite">
        <el-divider>发放新授权</el-divider>
        <el-form ref="grantFormRef" :model="grantForm" :rules="grantRules" label-width="80px">
          <el-form-item label="权限" prop="permission">
            <el-select v-model="grantForm.permission">
              <el-option v-for="item in grantableOptions" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="到期" prop="expires_at">
            <el-date-picker v-model="grantForm.expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" />
          </el-form-item>
          <el-form-item label="事由" prop="reason">
            <el-input v-model="grantForm.reason" maxlength="200" />
          </el-form-item>
          <el-button type="primary" :loading="grantSubmitting" @click="onCreateGrant">发放</el-button>
        </el-form>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminCreateGrant, adminCreateUser, adminListGrants, adminListProductLines,
  adminListUsers, adminReplaceUserLines, adminResetPassword, adminRevokeGrant, adminUpdateUser
} from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import { errorCode, errorText } from '../../../utils/admin'
import { formatDateTime } from '../../../utils/format'
import { hasPermission } from '../../../utils/permissions'

const ROLE_OPTIONS = [
  { value: 'super_admin', label: '超级管理员' },
  { value: 'supervisor', label: '售后主管' },
  { value: 'agent', label: '一线客服' },
  { value: 'auditor', label: '只读审计' }
]
const GRANTABLE = [
  'ticket:read', 'ticket:write', 'ticket:assign',
  'product:read', 'product:write', 'part:read', 'part:write',
  'fault:read', 'fault:write', 'upload:write', 'stats:read',
  'user:read', 'product_line:read', 'product_line:write'
]

const canWrite = hasPermission('user:write')
const currentUserId = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('user') || '{}').id
  } catch {
    return null
  }
})

const rows = ref([])
const lines = ref([])
const loading = ref(false)
const loadError = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const filters = reactive({ keyword: '', role: '', isActive: null })
const togglingId = ref(null)

const dialogVisible = ref(false)
const editingId = ref(null)
const submitting = ref(false)
const formRef = ref()
const form = reactive({ username: '', real_name: '', password: '', role: 'agent', product_lines: [] })

const passwordVisible = ref(false)
const resetPassword = ref('')

const grantsVisible = ref(false)
const grantUser = ref(null)
const grants = ref([])
const grantSubmitting = ref(false)
const grantFormRef = ref()
const grantForm = reactive({ permission: '', expires_at: '', reason: '' })

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  real_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入初始密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' }
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }]
}
const grantRules = {
  permission: [{ required: true, message: '请选择权限', trigger: 'change' }],
  expires_at: [{ required: true, message: '请选择到期时间', trigger: 'change' }],
  reason: [{ required: true, message: '请填写事由', trigger: 'blur' }]
}

const grantableOptions = computed(() => GRANTABLE)

function roleLabel(value) {
  return ROLE_OPTIONS.find((item) => item.value === value)?.label || value
}

let keywordTimer = null

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(filters.keyword.trim() ? { keyword: filters.keyword.trim() } : {}),
      ...(filters.role ? { role: filters.role } : {}),
      ...(filters.isActive === null || filters.isActive === undefined ? {} : { is_active: filters.isActive })
    }
    const data = await adminListUsers(params)
    rows.value = data.items
    pagination.total = data.total
  } catch (e) {
    rows.value = []
    pagination.total = 0
    loadError.value = errorText(e, '用户列表加载失败')
  } finally {
    loading.value = false
  }
}

async function loadLines() {
  try {
    const data = await adminListProductLines({ is_active: true })
    lines.value = data.items
  } catch {
    lines.value = []
  }
}

function reload() {
  pagination.page = 1
  load()
}

function onKeywordInput() {
  clearTimeout(keywordTimer)
  keywordTimer = setTimeout(reload, 300)
}

function onSizeChange() {
  pagination.page = 1
  load()
}

function resetForm() {
  editingId.value = null
  Object.assign(form, { username: '', real_name: '', password: '', role: 'agent', product_lines: [] })
  formRef.value?.clearValidate()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  resetForm()
  editingId.value = row.id
  Object.assign(form, {
    username: row.username,
    real_name: row.real_name,
    role: row.role,
    product_lines: row.product_lines.map((line) => ({
      line_id: line.id,
      expires_at: line.expires_at ? line.expires_at.slice(0, 10) : ''
    }))
  })
  dialogVisible.value = true
}

function addAssignment() {
  form.product_lines.push({ line_id: null, expires_at: '' })
}

function toExpiresAt(value) {
  return value ? `${value}T23:59:59+08:00` : null
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const assignments = form.product_lines
    .filter((item) => item.line_id)
    .map((item) => ({ line_id: item.line_id, expires_at: toExpiresAt(item.expires_at) }))

  submitting.value = true
  try {
    if (editingId.value) {
      await adminUpdateUser(editingId.value, {
        real_name: form.real_name.trim(),
        role: form.role
      })
      await adminReplaceUserLines(editingId.value, assignments)
    } else {
      await adminCreateUser({
        username: form.username.trim(),
        real_name: form.real_name.trim(),
        password: form.password,
        role: form.role,
        product_lines: assignments
      })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await load()
  } catch (e) {
    if (errorCode(e) === 'USERNAME_DUPLICATED') {
      ElMessage.error('账号已存在')
      return
    }
    ElMessage.error(errorText(e))
  } finally {
    submitting.value = false
  }
}

async function onToggleActive(row, value) {
  togglingId.value = row.id
  try {
    await adminUpdateUser(row.id, { is_active: value })
    row.is_active = value
    ElMessage.success(value ? '已启用' : '已停用')
  } catch (e) {
    ElMessage.error(errorText(e, '状态更新失败'))
    await load()
  } finally {
    togglingId.value = null
  }
}

async function onResetPassword(row) {
  try {
    await ElMessageBox.confirm(`确认重置「${row.real_name}」的密码？`, '重置密码', { type: 'warning' })
  } catch {
    return
  }
  try {
    const data = await adminResetPassword(row.id)
    resetPassword.value = data.password
    passwordVisible.value = true
  } catch (e) {
    ElMessage.error(errorText(e, '重置失败'))
  }
}

function openGrants(row) {
  grantUser.value = row
  grantsVisible.value = true
}

async function loadGrants() {
  if (!grantUser.value) return
  try {
    grants.value = await adminListGrants(grantUser.value.id)
  } catch (e) {
    ElMessage.error(errorText(e, '授权记录加载失败'))
  }
}

async function onCreateGrant() {
  const valid = await grantFormRef.value?.validate().catch(() => false)
  if (!valid) return
  grantSubmitting.value = true
  try {
    await adminCreateGrant(grantUser.value.id, { ...grantForm })
    ElMessage.success('已发放')
    Object.assign(grantForm, { permission: '', expires_at: '', reason: '' })
    await loadGrants()
  } catch (e) {
    ElMessage.error(errorText(e))
  } finally {
    grantSubmitting.value = false
  }
}

async function onRevoke(row) {
  try {
    await adminRevokeGrant(grantUser.value.id, row.id)
    ElMessage.success('已收回')
    await loadGrants()
  } catch (e) {
    ElMessage.error(errorText(e, '收回失败'))
  }
}

onMounted(async () => {
  await Promise.all([load(), loadLines()])
})
onBeforeUnmount(() => clearTimeout(keywordTimer))
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.kw { width: 200px; }
.role { width: 140px; }
.status { width: 120px; }
.name { font-weight: 600; }
.sub { color: #909399; font-size: 12px; }
.tag { margin-right: 4px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.assignments { display: flex; flex-direction: column; gap: 8px; }
.assignment-row { display: flex; gap: 8px; align-items: center; }
.line-select { width: 180px; }
.date { width: 160px; }
.password { margin-top: 16px; font-family: monospace; font-size: 18px; letter-spacing: 1px; }
</style>
```

- [ ] **Step 5: 加路由与菜单项**

路由：

```javascript
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('../views/admin/users/UserList.vue'),
        meta: { title: '用户管理', permission: 'user:read' }
      }
```

`Layout.vue` 的 `NAV_ITEMS` 追加：

```javascript
  { path: '/admin/users', label: '用户管理', permission: 'user:read' },
```

- [ ] **Step 6: 运行测试与 lint**

Run: `cd frontend && npm test -- src/views/admin/users/UserList.spec.js && npm run lint`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/admin/users frontend/src/api/admin.js frontend/src/router/index.js
git commit -m "feat(frontend): 用户管理页，含重置密码与临时授权"
```

---

## Task 13: 产品线管理页、产品页改造与只读态

**Files:**
- Create: `frontend/src/views/admin/product-lines/ProductLineList.vue`
- Create: `frontend/src/views/admin/product-lines/ProductLineList.spec.js`
- Modify: `frontend/src/views/admin/products/ProductList.vue`
- Modify: `frontend/src/views/admin/products/ProductList.spec.js`
- Modify: `frontend/src/views/admin/parts/PartList.vue`
- Modify: `frontend/src/views/admin/faults/FaultList.vue`
- Modify: `frontend/src/views/admin/faults/FaultEdit.vue`
- Modify: `frontend/src/components/ImageUpload.vue`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: 写失败测试（产品线页）**

```javascript
// frontend/src/views/admin/product-lines/ProductLineList.spec.js
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ProductLineList from './ProductLineList.vue'
import { setPermissions } from '../../../utils/permissions'

vi.mock('../../../api/admin', () => ({
  adminListProductLines: vi.fn(),
  adminCreateProductLine: vi.fn(),
  adminUpdateProductLine: vi.fn(),
  adminDeleteProductLine: vi.fn()
}))

import { adminListProductLines } from '../../../api/admin'

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['product_line:read', 'product_line:write'])
  adminListProductLines.mockResolvedValue({
    items: [{ id: 1, name: '扫地机', sort_order: 0, is_active: true, product_count: 3 }]
  })
})

describe('ProductLineList', () => {
  it('渲染产品线与产品数', async () => {
    const wrapper = mount(ProductLineList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.text()).toContain('扫地机')
    expect(wrapper.text()).toContain('3')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test -- src/views/admin/product-lines/ProductLineList.spec.js`
Expected: FAIL，组件不存在

- [ ] **Step 3: 实现产品线页**

```vue
<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>产品线管理</span>
          <el-button v-if="canWrite" type="primary" @click="openCreate">新增产品线</el-button>
        </div>
      </template>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table v-else v-loading="loading" :data="rows" row-key="id" border>
        <el-table-column prop="name" label="名称" min-width="200" />
        <el-table-column prop="product_count" label="产品数" width="100" align="center" />
        <el-table-column prop="sort_order" label="排序" width="100" align="center" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canWrite" label="操作" width="160" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑产品线' : '新增产品线'" width="420px" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="50" />
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" controls-position="right" />
        </el-form-item>
        <el-form-item label="启用" prop="is_active">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminCreateProductLine, adminDeleteProductLine, adminListProductLines, adminUpdateProductLine
} from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import { errorText } from '../../../utils/admin'
import { hasPermission } from '../../../utils/permissions'

const canWrite = hasPermission('product_line:write')
const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const dialogVisible = ref(false)
const editingId = ref(null)
const submitting = ref(false)
const formRef = ref()
const form = reactive({ name: '', sort_order: 0, is_active: true })
const rules = { name: [{ required: true, message: '请输入名称', trigger: 'blur' }] }

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    rows.value = (await adminListProductLines()).items
  } catch (e) {
    rows.value = []
    loadError.value = errorText(e, '产品线加载失败')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = null
  Object.assign(form, { name: '', sort_order: 0, is_active: true })
  formRef.value?.clearValidate()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  resetForm()
  editingId.value = row.id
  Object.assign(form, { name: row.name, sort_order: row.sort_order, is_active: row.is_active })
  dialogVisible.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (editingId.value) {
      await adminUpdateProductLine(editingId.value, { ...form, name: form.name.trim() })
    } else {
      await adminCreateProductLine({ ...form, name: form.name.trim() })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(errorText(e))
  } finally {
    submitting.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除产品线「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await adminDeleteProductLine(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(errorText(e, '删除失败'))
  }
}

onMounted(load)
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; }
</style>
```

- [ ] **Step 4: 产品页改为产品线下拉**

`ProductList.vue`：

1. `category` 列改为 `line_name`：`<el-table-column prop="line_name" label="产品线" width="120">`。
2. 表单里"分类"替换为：

```vue
        <el-form-item label="产品线" prop="line_id">
          <el-select v-model="form.line_id" placeholder="请选择产品线" class="line-select">
            <el-option v-for="line in lines" :key="line.id" :label="line.name" :value="line.id" />
          </el-select>
          <el-button v-if="canManageLines" link type="primary" class="manage" @click="$router.push('/admin/product-lines')">
            管理产品线
          </el-button>
        </el-form-item>
```

3. script 增加：

```javascript
import { hasPermission } from '../../../utils/permissions'
import { adminListProductLines } from '../../../api/admin'

const canManageLines = hasPermission('product_line:read')
const lines = ref([])

async function loadLines() {
  try {
    lines.value = (await adminListProductLines({ is_active: true })).items
  } catch {
    lines.value = []
  }
}
```

`form` 中 `category: ''` 改为 `line_id: null`；`rules` 加 `line_id: [{ required: true, message: '请选择产品线', trigger: 'change' }]`；`onSubmit` 的 payload 改为 `line_id: form.line_id`；`openEdit` 用 `line_id: row.line_id`；`onMounted` 同时调用 `load()` 与 `loadLines()`。

- [ ] **Step 5: 更新产品页测试**

`ProductList.spec.js` 的 mock 增加 `adminListProductLines`，返回 `{ items: [{ id: 1, name: '扫地机' }] }`；ROWS 的 `category` 改为 `line_id: 1, line_name: '扫地机'`；创建请求断言改为包含 `line_id: 1`。

- [ ] **Step 6: 现有后台页面按权限隐藏写操作**

只读审计拥有 `product:read`、`part:read`、`fault:read`，但页面现在假定"能进就能写"。按下面逐页处理，后端 403 仍是最终防线：

`ProductList.vue`：

```javascript
import { hasPermission } from '../../../utils/permissions'
const canWrite = hasPermission('product:write')
```

- "新增产品"按钮加 `v-if="canWrite"`
- 状态列的 `el-switch` 加 `:disabled="!canWrite"`
- 操作列 `<el-table-column v-if="canWrite" label="操作" ...>`
- `@row-click` 改为 `@row-click="onRowClick"`，函数体第一行 `if (!canWrite) return`，再调用 `openEdit(row)`

`PartList.vue`：同样的写法，权限换成 `part:write`，隐藏"新增零件"、编辑/删除按钮。

`FaultList.vue`：

```javascript
import { hasPermission } from '../../../utils/permissions'
const canWrite = hasPermission('fault:write')
// 能进详情页的条件：能读故障 + 能读产品/零件（编辑页依赖这两个下拉）
const canOpen = hasPermission('fault:read') && hasPermission('product:read') && hasPermission('part:read')
```

- "新增故障"、编辑、删除按钮加 `v-if="canWrite"`
- `@row-click` 改为 `@row-click="onRowClick"`，函数体第一行 `if (!canOpen) return`
- 说明：一线客服只有 `fault:read`，可在列表看标题，但不能进入编辑页；方案详情走客户侧公开页面（同一份数据）

`FaultEdit.vue`：只读角色可查看方案详情，但不能保存或上传。路由权限改为 `fault:read`（见 Step 7），组件内：

```javascript
import { hasPermission } from '../../../utils/permissions'
const canWrite = hasPermission('fault:write')
```

- "保存"按钮加 `v-if="canWrite"`
- 根 `el-form` 加 `:disabled="!canWrite"`（Element Plus 会禁用全部子控件）
- 所有 `ImageUpload` 加 `:readonly="!canWrite"`

`ImageUpload.vue` 增加只读支持：

```javascript
const props = defineProps({
  modelValue: { type: String, default: null },
  readonly: { type: Boolean, default: false }
})
```

模板里把 `.ops` 整个 div 加 `v-if="!readonly"`（预览与放大仍可用）。

- [ ] **Step 7: 加 P-19 路由**

```javascript
      {
        path: 'product-lines',
        name: 'admin-product-lines',
        component: () => import('../views/admin/product-lines/ProductLineList.vue'),
        meta: { title: '产品线管理', permission: 'product_line:read' }
      }
```

同时把故障编辑路由的 `meta` 改为：

```javascript
        meta: { title: '故障编辑', permission: 'fault:read', requires: ['product:read', 'part:read'] }
```

路由守卫（Task 11 中）需支持 `requires`：

```javascript
  if (to.meta.requires && !to.meta.requires.every(hasPermission)) {
    return { path: '/admin/faults' }
  }
```

这样一线客服直接拼 `/admin/faults/edit/1` 会被挡回列表，不会加载产品/零件下拉时收到 403。

- [ ] **Step 8: 运行测试**

Run: `cd frontend && npm test -- src/views/admin/product-lines/ProductLineList.spec.js src/views/admin/products/ProductList.spec.js && npm run lint`
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add frontend/src/views/admin/product-lines frontend/src/views/admin/products \
  frontend/src/views/admin/parts frontend/src/views/admin/faults \
  frontend/src/components/ImageUpload.vue frontend/src/router/index.js
git commit -m "feat(frontend): 产品线管理页，现有后台页按权限进入只读态"
```

---

## Task 14: 工单抽屉改派

**Files:**
- Modify: `frontend/src/views/admin/tickets/TicketDrawer.vue`
- Modify: `frontend/src/views/admin/tickets/TicketDrawer.spec.js`

- [ ] **Step 1: 写失败测试**

```javascript
// 追加到 TicketDrawer.spec.js
import { setPermissions } from '../../../utils/permissions'

it('主管可见处理人下拉，并按产品线请求候选人', async () => {
  setPermissions(['ticket:read', 'ticket:write', 'ticket:assign'])
  adminListAssignable.mockResolvedValue([{ id: 9, real_name: '王伟' }])

  const wrapper = await mountDrawer(1)

  expect(wrapper.text()).toContain('处理人')
  expect(adminListAssignable).toHaveBeenCalledWith({ product_id: 1 })
})
```

其中 `adminListAssignable` 需加入该文件已有的 `vi.mock('../../../api/admin')` 工厂与 import 列表；`makeDetail()` 默认 `product.id = 1`，与断言一致。

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test -- src/views/admin/tickets/TicketDrawer.spec.js`
Expected: FAIL，没有"处理人"下拉

- [ ] **Step 3: 修改组件**

模板在"状态"表单项**之后**加入（不能放在之前：E2E 用 `.el-select` 的第一个元素选状态流转，插到前面会把选择器指到处理人）：

```vue
          <el-form-item v-if="canAssign" label="处理人">
            <el-select v-model="form.assignee_id" clearable placeholder="不修改" class="wd">
              <el-option
                v-for="user in assignable"
                :key="user.id"
                :label="user.real_name"
                :value="user.id"
              />
            </el-select>
          </el-form-item>
```

script：

```javascript
import { adminGetTicket, adminListAssignable, adminUpdateTicket } from '../../../api/admin'
import { hasPermission } from '../../../utils/permissions'

const canWrite = hasPermission('ticket:write')
const canAssign = hasPermission('ticket:assign')
const assignable = ref([])

async function loadAssignable(productId) {
  if (!canAssign || !productId) {
    assignable.value = []
    return
  }
  try {
    assignable.value = await adminListAssignable({ product_id: productId })
  } catch {
    assignable.value = []
  }
}

// load() 内拿到 data 后调用
async function load() {
  const data = await adminGetTicket(props.ticketId)
  detail.value = data
  resetForm(data)
  await loadAssignable(data.product?.id || null)
}
```

只读角色（只读审计）不显示处理表单：把 `<h4 class="block-title">处理</h4>` 与其后的 `<el-form ...>` 整段包进 `<template v-if="canWrite">`，历史记录保持展示。


`form` 增加 `assignee_id: null`，`resetForm` 置空；`onSave` 中：

```javascript
  if (canAssign && form.assignee_id && form.assignee_id !== detail.value.assignee_id) {
    payload.assignee_id = form.assignee_id
  }
```

- [ ] **Step 4: 运行测试**

Run: `cd frontend && npm test -- src/views/admin/tickets/TicketDrawer.spec.js`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/admin/tickets
git commit -m "feat(frontend): 工单抽屉支持改派处理人"
```

---

## Task 15: 联调工具、种子与 E2E

**Files:**
- Modify: `scripts/dev/seed_demo.py:176-185`
- Modify: `scripts/dev/check_orm_pg.py:50`
- Modify: `frontend/e2e/main-flow.spec.js`

- [ ] **Step 1: seed_demo 先建产品线**

在创建产品**循环之前**调用一次，并把结果传给循环：

```python
    lines = ensure_lines(client, PRODUCTS)

    for spec in PRODUCTS:
        ...
        product = client.post(
            "/api/admin/products",
            json={
                "name": spec["name"],
                "model": spec["model"],
                "line_id": lines[spec["category"]],
                "description": spec["description"],
                "sort_order": spec["sort_order"],
            },
        ).json()
```

`ensure_lines` 函数定义：

```python
def ensure_lines(client, specs):
    existing = {item["name"]: item for item in client.get("/api/admin/product-lines").json()["items"]}
    mapping = {}
    for spec in specs:
        name = spec["category"]
        if name not in existing:
            existing[name] = client.post(
                "/api/admin/product-lines", json={"name": name, "sort_order": 0}
            ).json()
        mapping[name] = existing[name]["id"]
    return mapping
```

- [ ] **Step 2: check_orm_pg 改为产品线**

```python
    line = ProductLine(name="验证线", sort_order=999)
    s.add(line)
    s.flush()
    product = Product(name="联调验证机", model="ORMTEST-X1", line_id=line.id, sort_order=999)
```

同时在该文件顶部把 `ProductLine` 加入 `from app.models import ...`。

- [ ] **Step 3: verify_schema.mjs 适配新表与必填 line_id**

`scripts/dev/verify_schema.mjs`：

1. 表清单改为：

```javascript
  const want = [
    'faults', 'parts', 'product_lines', 'products', 'query_logs',
    'schema_migrations', 'ticket_status_logs', 'tickets',
    'user_permission_grants', 'user_product_lines', 'users'
  ]
```

2. "删除故障时引用置 NULL" 用例里，产品插入前先建产品线：

```javascript
  const line = await db.query(`INSERT INTO product_lines (name) VALUES ('扫地机') RETURNING id`)
  const lineId = line.rows[0].id
  const p = await db.query(
    `INSERT INTO products (name,model,line_id) VALUES ('扫地机','X1',$1) RETURNING id`,
    [lineId]
  )
```

3. "删除有零件的产品被 RESTRICT 阻止" 用例同样先建一条产品线（可复用上一步的 `lineId`，但每个 check 独立执行，需在该 check 内新建）：

```javascript
  const line = await db.query(`INSERT INTO product_lines (name) VALUES ('净化器线') RETURNING id`)
  const p = await db.query(
    `INSERT INTO products (name,model,line_id) VALUES ('净化器','A2',$1) RETURNING id`,
    [line.rows[0].id]
  )
```

4. 末尾 `SELECT id FROM products WHERE model='X1'` 无需改（产品已由第 2 步插入）。

- [ ] **Step 4: E2E 菜单断言**

`main-flow.spec.js` 在第 4 段登录成功、`toHaveURL(/\/admin\/tickets/)` 之后追加一行：

```javascript
  // 超级管理员应看到用户管理入口
  await expect(page.getByRole('menuitem', { name: '用户管理' })).toBeVisible()
```

- [ ] **Step 5: 运行全量测试**

Run:
```bash
pytest -q
npm run verify:schema
cd frontend && npm test && npm run lint && npm run build
```
Expected: 后端全部 PASS；schema 校验通过（11 张表）；前端全部 PASS；lint 0 error；build 成功

- [ ] **Step 6: 提交**

```bash
git add scripts/dev frontend/e2e
git commit -m "test: 联调种子与 E2E 适配产品线及用户管理"
```

---

## Task 16: 文档同步与最终验证

**Files:**
- Modify: `docs/00-项目管理/项目章程.md`
- Modify: `docs/00-项目管理/WBS任务拆解.md`
- Modify: `docs/00-项目管理/排期计划.md`
- Modify: `docs/01-需求设计/PRD产品需求文档.md`
- Modify: `docs/01-需求设计/页面清单与交互说明.md`
- Modify: `docs/01-需求设计/用户故事清单.md`
- Modify: `docs/02-技术设计/API接口契约.md`
- Modify: `docs/02-技术设计/系统架构设计.md`
- Modify: `docs/完整分期路线图.md`
- Modify: `docs/03-测试与验收/测试用例清单.md`
- Modify: `docs/03-测试与验收/验收检查表.md`
- Modify: `docs/04-运维与运营/运维手册.md`
- Modify: `docs/05-评估审查/01-需求基线清单.md`
- Modify: `docs/05-评估审查/03-评估审查报告.md`

- [ ] **Step 1: 按设计稿第 11 节逐项修改**

每份文档的具体修改点以 `docs/superpowers/specs/2026-10-22-user-permissions-design.md` §11 为准，逐条落地：

1. 章程：用户与权限管理从"三期"移到"一期上线前追加"；风险表移除"无用户管理"。
2. WBS/排期：追加本次任务卡（T1–T16）与工期，不改一期历史数据。
3. PRD：角色表改四角色；删除 §5"一期不做用户与权限管理"；产品"分类"改"产品线"。
4. 页面清单：新增 P-18、P-19；P-13 增加产品线下拉；P-12 增加处理人下拉；后台页面总数改为 14。
5. 用户故事：新增"管理员管理账号""客服只看自己产品线工单""临时授权到期失效"三条。
6. API 契约：删除 §0.3"role 不参与鉴权"；§1 登录响应加 `permissions`，新增 `/auth/me`；§2 产品改 `line_id/line_name`；§5 工单说明数据范围与改派；新增用户管理与产品线章节；§7 加 `PERMISSION_DENIED`、`USERNAME_DUPLICATED`、`LINE_NAME_DUPLICATED`、`LAST_SUPER_ADMIN`、`INVALID_PERMISSION`、`ASSIGNEE_OUT_OF_SCOPE`、`SELF_DISABLE`、`SELF_ROLE_CHANGE`、`USER_DISABLED`、`ASSIGNEE_DISABLED`、`ASSIGNEE_NO_PERMISSION`、`LINE_INACTIVE`。
7. 架构设计：鉴权层、产品线模型、迁移机制、部署顺序。
8. 路线图 3.5：标注"角色与操作权限已提前落地；数据权限限工单；操作日志仍留三期"。
9. 测试用例：新增角色矩阵、数据范围、临时授权、改派、产品线用例。
10. 验收检查表：加设计稿 §10 的 8 条验收标准。
11. 运维手册：账号维护改为界面；脚本保留兜底；迁移执行与恢复后迁移。
12. 需求基线与评估报告：C-06 裁决改为"提前实施权限子集"，R-A-15 状态更新。

- [ ] **Step 2: 检查文档引用与链接**

Run: `python scripts/dev/check_links.py`
Expected: 0 条失效链接

- [ ] **Step 3: 对照设计稿 §10 的 8 条验收标准逐项核对**

在 PR 描述或验收记录中写下证据，不能只写"已实现"：

| # | 验收项 | 证据 |
|---|---|---|
| 1 | 四角色菜单与接口符合矩阵，越权 403 | `test_permission_endpoints.py` 全绿 + 手动登录四个角色截图菜单 |
| 2 | 客服只看本产品线工单，空产品线 0 条，空产品工单不可见 | `test_ticket_scope.py` 四个用例全绿 |
| 3 | 超管可完成建号/停用/启用/重置密码/改角色/分配产品线/发收回授权 | `test_admin_users.py`、`test_grants.py` 全绿 + 手动走一遍 P-18 |
| 4 | 临时授权到期失效、提前收回立即失效 | `test_permissions.py`、`test_grants.py` 对应用例 |
| 5 | 不能停用自己/改自己角色/最后一个超管保护 | `test_admin_users.py` 自保护与守卫用例 |
| 6 | 现有 admin 迁移后权限完整，category 正确映射 | 在带旧数据的库上跑 `docker compose run --rm migrate`，登录 admin 检查菜单与产品线 |
| 7 | 产品线可维护，被引用时删除 409 | `test_product_lines.py` 全绿 |
| 8 | 主管可改派同线客服，客服无改派入口，候选人过滤正确 | `test_ticket_assign.py` 全绿 + 手动打开工单抽屉看下拉 |

- [ ] **Step 4: 最终验证**

Run:
```bash
pytest -q
npm run verify:schema
cd frontend && npm test && npm run lint && npm run build
python scripts/dev/check_links.py
```
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add docs
git commit -m "docs: 用户权限、产品线与迁移机制同步到需求/契约/验收/运维文档"
```

---

## 自查记录（含第二轮复审修订）

- **Spec 覆盖**：角色矩阵（T3）、角色值与 init_admin 迁移（T2）、产品线（T2/T6）、数据范围（T7）、临时授权（T3/T9）、用户管理（T8）、改派（T10）、前端权限与只读态（T11–T14）、迁移机制与部署顺序（T1）、文档（T16）。
- **第二轮复审补丁**：
  1. 迁移前增加 `backup.sh` 备份并失败即中止（设计稿 §8.3 要求，原计划漏了）。
  2. 临时授权增加"不能授予自己不具备的权限"校验（设计稿 §4.3）。
  3. `Product.line_id` 非空会打挂 5 个测试文件的造数助手，T6 增加全局夹具改造步骤。
  4. `scripts/dev/verify_schema.mjs` 固定 7 张表且产品插入不带 `line_id`，T15 补齐。
  5. T16 增加逐条验收证据表，避免"实现了但没验"。
- **类型一致性**：`UserProductLine`、`UserPermissionGrant`、`ProductLine` 在模型、schema、服务、测试中名称一致；权限常量统一由 `app.core.permissions` 导出；`ticket:assign` 在权限码表、角色矩阵、接口表格、前端菜单与测试中保持一致。
