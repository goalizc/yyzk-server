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
