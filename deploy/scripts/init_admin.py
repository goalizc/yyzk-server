#!/usr/bin/env python3
"""
初始化后台管理员账号（幂等）

背景：bcrypt 哈希必须在运行时生成，无法写死在 schema.sql 里。
      此前 schema.sql 内置的哈希是无效占位值，导致 admin 无法登录。

用法（推荐，一次性任务）：
    docker compose run --rm init

用法（已部署环境内直接执行）：
    docker compose exec backend python /app/scripts/init_admin.py

环境变量：
    DATABASE_URL        必填，如 postgresql+psycopg2://fault:pwd@db:5432/fault_db
    ADMIN_INIT_PASSWORD 必填，≥8 位，无默认值（避免线上留已知口令）
    ADMIN_USERNAME      选填，默认 admin
    ADMIN_REAL_NAME     选填，默认 系统管理员

行为：
    - 账号不存在 → 创建
    - 账号已存在 → 默认跳过（幂等，重复执行安全）
    - 加 --reset-password 参数 → 强制重置密码（用于找回）
"""

import argparse
import os
import sys

from passlib.context import CryptContext
from sqlalchemy import create_engine, text

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化后台管理员账号")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="账号已存在时强制重置密码（默认跳过）",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[init_admin] 缺少环境变量 DATABASE_URL", file=sys.stderr)
        return 2

    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_INIT_PASSWORD")
    real_name = os.getenv("ADMIN_REAL_NAME", "系统管理员")

    if not password:
        print("[init_admin] 缺少环境变量 ADMIN_INIT_PASSWORD（不提供默认口令）", file=sys.stderr)
        return 2
    if len(password) < 8:
        print("[init_admin] ADMIN_INIT_PASSWORD 至少 8 位", file=sys.stderr)
        return 2

    engine = create_engine(database_url, pool_pre_ping=True)
    password_hash = pwd_context.hash(password)

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM users WHERE username = :u"), {"u": username}
        ).fetchone()

        if row is None:
            conn.execute(
                text(
                    """
                    INSERT INTO users (username, password_hash, real_name, role, is_active)
                    VALUES (:u, :p, :r, 'admin', TRUE)
                    """
                ),
                {"u": username, "p": password_hash, "r": real_name},
            )
            print(f"[init_admin] 已创建管理员 {username}（初始密码见 ADMIN_INIT_PASSWORD）")
        elif args.reset_password:
            conn.execute(
                text("UPDATE users SET password_hash = :p, updated_at = NOW() WHERE id = :id"),
                {"p": password_hash, "id": row[0]},
            )
            print(f"[init_admin] 已重置 {username} 的密码")
        else:
            print(f"[init_admin] 管理员 {username} 已存在，跳过（加 --reset-password 可重置）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
