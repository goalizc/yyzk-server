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
