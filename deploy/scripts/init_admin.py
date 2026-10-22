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

用户管理（也可在界面维护；本脚本作为运维兜底入口）：
    python init_admin.py user list                   列出全部账号
    python init_admin.py user add wangwei             新建客服（密码自动生成并打印一次）
    python init_admin.py user disable wangwei         停用（离职），保留历史工单归属
    python init_admin.py user enable wangwei          启用
    python init_admin.py user passwd wangwei          重置密码（无需原密码）

    为什么停用而不是删除：tickets.assignee_id 与 ticket_logs.operator_id 都指向
    users.id，删账号会让历史工单的"谁处理的"变成悬空外键。停用后 is_active=false，
    登录被拒但历史记录完整。
"""

import argparse
import os
import secrets
import string
import sys

from passlib.context import CryptContext
from sqlalchemy import create_engine, text

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _gen_password(length: int = 12) -> str:
    """生成随机密码。排除易混字符 0/O/1/l/I，避免口头传达或手抄时出错。"""
    alphabet = "".join(
        c for c in string.ascii_letters + string.digits if c not in "0O1lI"
    )
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _require_database_url() -> str | None:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("[init_admin] 缺少环境变量 DATABASE_URL", file=sys.stderr)
        return None
    return url


def cmd_init(args) -> int:
    """原行为：初始化 / 重置管理员。"""
    database_url = _require_database_url()
    if not database_url:
        return 2

    username = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
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
                    VALUES (:u, :p, :r, 'super_admin', TRUE)
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


def cmd_user(args) -> int:
    """用户管理子命令。"""
    database_url = _require_database_url()
    if not database_url:
        return 2

    engine = create_engine(database_url, pool_pre_ping=True)

    if args.action == "list":
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT username, real_name, role, is_active, last_login_at, created_at
                    FROM users ORDER BY is_active DESC, username
                    """
                )
            ).fetchall()
        if not rows:
            print("[init_admin] 没有任何账号")
            return 0
        print(f"{'账号':<16}{'姓名':<14}{'角色':<8}{'状态':<6}{'最近登录'}")
        print("-" * 66)
        for u, name, role, active, last_login, _ in rows:
            state = "启用" if active else "已停用"
            # last_login 为 None 时 IS NULL 判断要显式，不能靠格式化兜底
            last = last_login.strftime("%Y-%m-%d %H:%M") if last_login else "从未登录"
            print(f"{u:<16}{name or '':<14}{role:<8}{state:<6}{last}")
        print(f"\n共 {len(rows)} 个账号，其中启用 {sum(1 for r in rows if r[3])} 个")
        return 0

    username = args.username
    if not username:
        print("[init_admin] 缺少账号名", file=sys.stderr)
        return 2

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, is_active FROM users WHERE username = :u"), {"u": username}
        ).fetchone()

        if args.action == "add":
            if row is not None:
                print(f"[init_admin] 账号 {username} 已存在，未做改动", file=sys.stderr)
                return 1
            password = args.password or _gen_password()
            if len(password) < 8:
                print("[init_admin] 密码至少 8 位", file=sys.stderr)
                return 2
            conn.execute(
                text(
                    """
                    INSERT INTO users (username, password_hash, real_name, role, is_active)
                    VALUES (:u, :p, :r, :role, TRUE)
                    """
                ),
                {
                    "u": username,
                    "p": pwd_context.hash(password),
                    "r": args.real_name or username,
                    "role": args.role,
                },
            )
            print(f"[init_admin] 已创建账号 {username}（角色 {args.role}）")
            if not args.password:
                # 只打印这一次：库里只有哈希，之后无法再查出明文
                print(f"[init_admin] 初始密码：{password}")
                print("[init_admin] 请通过安全渠道交给本人，并要求首次登录后修改")
            return 0

        if row is None:
            print(f"[init_admin] 账号 {username} 不存在", file=sys.stderr)
            return 1

        user_id, is_active = row

        if args.action == "disable":
            if not is_active:
                print(f"[init_admin] 账号 {username} 已是停用状态")
                return 0
            conn.execute(
                text("UPDATE users SET is_active = FALSE, updated_at = NOW() WHERE id = :id"),
                {"id": user_id},
            )
            print(f"[init_admin] 已停用 {username}（历史工单归属保留）")
        elif args.action == "enable":
            if is_active:
                print(f"[init_admin] 账号 {username} 已是启用状态")
                return 0
            conn.execute(
                text("UPDATE users SET is_active = TRUE, updated_at = NOW() WHERE id = :id"),
                {"id": user_id},
            )
            print(f"[init_admin] 已启用 {username}")
        elif args.action == "passwd":
            password = args.password or _gen_password()
            if len(password) < 8:
                print("[init_admin] 密码至少 8 位", file=sys.stderr)
                return 2
            conn.execute(
                text("UPDATE users SET password_hash = :p, updated_at = NOW() WHERE id = :id"),
                {"p": pwd_context.hash(password), "id": user_id},
            )
            print(f"[init_admin] 已重置 {username} 的密码")
            if not args.password:
                print(f"[init_admin] 新密码：{password}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化管理员 / 维护后台账号")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="账号已存在时强制重置密码（默认跳过）",
    )

    sub = parser.add_subparsers(dest="command")
    p_user = sub.add_parser("user", help="账号维护（列表/新建/停用/启用/重置密码）")
    p_user.add_argument(
        "action", choices=["list", "add", "disable", "enable", "passwd"]
    )
    p_user.add_argument("username", nargs="?", help="账号名（list 时不需要）")
    p_user.add_argument("--password", help="显式指定密码；不传则随机生成并打印一次")
    p_user.add_argument("--real-name", dest="real_name", help="真实姓名，默认同账号名")
    p_user.add_argument(
        "--role",
        default="agent",
        choices=["super_admin", "supervisor", "agent", "auditor"],
        help="角色，默认 agent",
    )

    args = parser.parse_args()
    if args.command == "user":
        return cmd_user(args)
    return cmd_init(args)


if __name__ == "__main__":
    raise SystemExit(main())
