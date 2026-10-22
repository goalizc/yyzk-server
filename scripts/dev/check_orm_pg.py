#!/usr/bin/env python3
"""ORM 与 deploy/schema.sql 对齐检查（需要一个真实 PostgreSQL）。

单测跑在 SQLite 上，验证不到 JSONB、CHECK、部分索引、TIMESTAMPTZ 这些 PG 专属行为；
本脚本在真库上把 7 张表都写一遍，确认模型与 DDL 没有漂移。

用法（没有原生 PostgreSQL 时，可配合 node scripts/dev/pg_server.mjs）：
    node scripts/dev/pg_server.mjs &            # WASM PostgreSQL，监听 55432
    DATABASE_URL=postgresql+psycopg2://postgres@127.0.0.1:55432/postgres \
    JWT_SECRET=$(openssl rand -hex 32) \
    .venv/bin/python scripts/dev/check_orm_pg.py

退出码：0 全部通过；1 有失败项。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("JWT_SECRET", "orm-check-secret-0123456789abcdef012345")

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import get_engine  # noqa: E402
from app.models import Fault, Part, Product, ProductLine, Ticket, TicketStatusLog, User  # noqa: E402

results: list[str] = []


def check(name: str, fn) -> None:
    fn()
    results.append(name)
    print(f"  PASS  {name}")


def main() -> int:
    url = os.getenv("DATABASE_URL", "")
    if "postgresql" not in url:
        print("[check_orm_pg] 需要 PostgreSQL 的 DATABASE_URL", file=sys.stderr)
        return 1

    engine = get_engine()
    with Session(engine) as s:
        line = ProductLine(name="验证线", sort_order=999)
        s.add(line)
        s.flush()
        product = Product(name="联调验证机", model="ORMTEST-X1", line_id=line.id, sort_order=999)
        s.add(product)
        s.flush()
        part = Part(product_id=product.id, part_no="P-ORM-001", name="主刷模组", group_name="动力系统")
        s.add(part)
        s.flush()

        fault = Fault(
            product_id=product.id,
            part_id=part.id,
            title="开机无反应",
            symptom="指示灯不亮",
            solution_steps=[{"step": 1, "text": "检查适配器", "image_url": None}],
            attachment_urls=[{"name": "手册.pdf", "url": "/uploads/x.pdf", "size": 1024}],
            needs_professional=True,
        )
        s.add(fault)
        s.flush()
        check("产品 / 零件 / 故障写入", lambda: None)

        def jsonb_round_trip() -> None:
            s.flush()
            s.expire_all()
            row = s.get(Fault, fault.id)
            assert isinstance(row.solution_steps, list), "solution_steps 不是数组"
            assert row.solution_steps[0]["step"] == 1, "solution_steps 内容不对"
            assert row.attachment_urls[0]["size"] == 1024, "attachment_urls 内容不对"
            assert row.created_at.tzinfo is not None, "created_at 不带时区"

        check("JSONB 往返 + TIMESTAMPTZ 带时区", jsonb_round_trip)

        ticket = Ticket(
            ticket_no="TK202610200001",
            product_id=product.id,
            part_id=part.id,
            fault_id=fault.id,
            contact="13800138000",
            description="验证用：开机无反应，已按方案排查未解决",
            need_on_site=True,
        )
        s.add(ticket)
        s.flush()
        s.add(TicketStatusLog(ticket_id=ticket.id, from_status=None, to_status="open", remark="建单"))
        s.commit()  # 先落库：下面的违例检查会 rollback
        check("工单 + 状态日志写入", lambda: None)

        def ticket_no_check() -> None:
            try:
                s.add(Ticket(ticket_no="TK20261020001", contact="13800138000", description="三位序号应被拒绝"))
                s.flush()
            except Exception:
                s.rollback()
                return
            s.rollback()
            raise AssertionError("3 位序号的工单号未被 CHECK 拒绝")

        check("工单号格式 CHECK 生效", ticket_no_check)
        check("v_fault_stats 视图可查", lambda: s.execute(text("SELECT * FROM v_fault_stats")).all())

        tid, fid, pid = ticket.id, fault.id, product.id

        def delete_sets_null() -> None:
            s.execute(text("DELETE FROM faults WHERE id = :i"), {"i": fid})
            s.commit()
            s.expire_all()
            assert s.get(Ticket, tid).fault_id is None, "删除故障后 fault_id 未置 NULL"

        check("删除故障后工单引用置 NULL", delete_sets_null)

        def last_login_tz() -> None:
            user = s.scalar(select(User).where(User.username == "admin"))
            if user is None:
                return  # 未跑过 init_admin，跳过
            assert user.last_login_at is None or user.last_login_at.tzinfo is not None

        check("users.last_login_at 时区正确（未初始化则跳过）", last_login_tz)

        # 清理
        s.execute(text("DELETE FROM ticket_status_logs WHERE ticket_id = :t"), {"t": tid})
        s.execute(text("DELETE FROM tickets WHERE id = :t"), {"t": tid})
        s.execute(text("DELETE FROM parts WHERE product_id = :p"), {"p": pid})
        s.execute(text("DELETE FROM products WHERE id = :p"), {"p": pid})
        s.execute(text("DELETE FROM product_lines WHERE name = :n"), {"n": "验证线"})
        s.commit()

    print(f"\n结果：{len(results)} 项通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
