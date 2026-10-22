"""看板数据范围：临时授予 stats:read 的 LINES 角色只能看到本产品线数据。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import (
    Product,
    ProductLine,
    QueryLog,
    Ticket,
    UserPermissionGrant,
    UserProductLine,
)
from tests.conftest import auth_headers, login, make_user


def _setup(db):
    line_a = ProductLine(name="扫地机")
    line_b = ProductLine(name="净化器")
    db.add_all([line_a, line_b])
    db.flush()
    product_a = Product(line_id=line_a.id, name="扫地机A", model="A1")
    product_b = Product(line_id=line_b.id, name="净化器B", model="B1")
    db.add_all([product_a, product_b])
    db.flush()
    db.add_all(
        [
            Ticket(
                ticket_no="TK202610220101",
                product_id=product_a.id,
                contact="13800000001",
                description="A 线工单",
            ),
            Ticket(
                ticket_no="TK202610220102",
                product_id=product_b.id,
                contact="13800000002",
                description="B 线工单",
            ),
            QueryLog(product_id=product_a.id, fault_id=None, raw_query="a线未命中", hit=False),
            QueryLog(product_id=product_b.id, fault_id=None, raw_query="b线未命中", hit=False),
        ]
    )
    db.commit()
    return line_a, line_b, product_a, product_b


def _grant_stats_read(db, user) -> None:
    db.add(
        UserPermissionGrant(
            user_id=user.id,
            permission="stats:read",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            reason="临时看板",
        )
    )
    db.commit()


def test_agent_overview_scoped_to_own_line(client, db) -> None:
    line_a, _, _, _ = _setup(db)
    agent = make_user(db, username="agent1", role="agent")
    db.add(UserProductLine(user_id=agent.id, line_id=line_a.id))
    db.commit()
    _grant_stats_read(db, agent)
    headers = auth_headers(login(client, "agent1")["access_token"])

    body = client.get("/api/admin/stats/overview", headers=headers).json()

    assert body["total_tickets"] == 1
    assert body["total_queries"] == 1


def test_agent_missed_scoped_to_own_line(client, db) -> None:
    line_a, _, _, _ = _setup(db)
    agent = make_user(db, username="agent1", role="agent")
    db.add(UserProductLine(user_id=agent.id, line_id=line_a.id))
    db.commit()
    _grant_stats_read(db, agent)
    headers = auth_headers(login(client, "agent1")["access_token"])

    body = client.get("/api/admin/stats/missed", headers=headers).json()

    assert [item["raw_query"] for item in body] == ["a线未命中"]


def test_supervisor_overview_sees_all_lines(client, db) -> None:
    _setup(db)
    make_user(db, username="boss", role="supervisor")
    headers = auth_headers(login(client, "boss")["access_token"])

    body = client.get("/api/admin/stats/overview", headers=headers).json()

    assert body["total_tickets"] == 2
    assert body["total_queries"] == 2
