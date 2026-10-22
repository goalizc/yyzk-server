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
