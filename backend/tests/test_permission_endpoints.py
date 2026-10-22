"""后台接口按权限码鉴权：四角色 × 读接口，以及写接口的拒绝路径。"""

import pytest

from app.core.permissions import effective_permissions
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
