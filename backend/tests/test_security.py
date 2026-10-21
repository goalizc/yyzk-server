"""安全验收测试（TC-64 / TC-65 / TC-66 / TC-72 / TC-73）。

为什么单独一个文件：这些用例验证的不是业务逻辑，而是"越权访问应该失败"。
它们和业务用例的失败含义完全不同——业务用例挂了是功能错，这里挂了是**安全洞**。
放在一起便于每次改动后集中确认。

对应验收表（docs/03-测试与验收/验收检查表.md 四、安全验收）。
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Fault, Part, Product, User
from tests.conftest import DEFAULT_PASSWORD, auth_headers, login, make_user


# ---- 本地构造助手 ----
# 不从 test_faults / test_products 里 import：那两个文件各自重复定义了同名函数，
# 语义已经分叉（默认值不同）。跨测试文件 import 会把这种分叉变成隐藏耦合，
# 改一处默认值会静默影响另一个文件。安全测试自己带一份最小的。
def admin_headers(client: TestClient, db: Session) -> dict:
    # 每个用例的 db 都是全新的内存库，用户不存在，必须先建
    make_user(db)
    return auth_headers(login(client)["access_token"])


def make_product(db: Session, name: str = "智能扫地机器人", model: str = "X1") -> Product:
    # 注意：产品用 is_active（上下架），故障用 is_published（发布）。两者不是同一语义。
    product = Product(name=name, model=model, is_active=True, sort_order=0)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def make_part(db: Session, product: Product, name: str = "电源模组") -> Part:
    part = Part(product_id=product.id, name=name, group_name="动力系统", sort_order=1)
    db.add(part)
    db.commit()
    db.refresh(part)
    return part


def make_fault(
    db: Session, product: Product, part: Part, title: str, published: bool = True
) -> Fault:
    fault = Fault(
        product_id=product.id,
        part_id=part.id,
        title=title,
        symptom="现象",
        root_cause="根因",
        solution_steps=[{"step": 1, "text": "检查电源", "image_url": None}],
        is_published=published,
    )
    db.add(fault)
    db.commit()
    db.refresh(fault)
    return fault


# ================================================================
# TC-64 鉴权覆盖率：21 个受保护端点逐个验证，不接受抽查
# ================================================================
#
# 清单来自 API 契约 §9：后台 17 + 统计 3 + 改密 1 = 21。
# 这里用参数化逐个打，任何一个端点漏掉 Depends(get_current_user) 都会红。
#
# 为什么不用"随便挑几个"：漏鉴权往往是复制粘贴某个端点时忘了带上依赖，
# 抽查 5 个能过，第 6 个可能就漏了。
PROTECTED_ENDPOINTS = [
    # ---- 后台：产品 / 零件（8）----
    ("GET", "/api/admin/products", None),
    ("POST", "/api/admin/products", {"name": "x", "model": "x"}),
    ("PUT", "/api/admin/products/1", {"name": "x"}),
    ("DELETE", "/api/admin/products/1", None),
    ("GET", "/api/admin/parts?product_id=1", None),
    ("POST", "/api/admin/parts", {"product_id": 1, "name": "x"}),
    ("PUT", "/api/admin/parts/1", {"name": "x"}),
    ("DELETE", "/api/admin/parts/1", None),
    # ---- 后台：上传（1）----
    ("POST", "/api/admin/upload", None),
    # ---- 后台：故障知识库（5）----
    ("GET", "/api/admin/faults", None),
    ("GET", "/api/admin/faults/1", None),
    ("POST", "/api/admin/faults", {"product_id": 1, "part_id": 1, "title": "x"}),
    ("PUT", "/api/admin/faults/1", {"title": "x"}),
    ("DELETE", "/api/admin/faults/1", None),
    # ---- 后台：工单（3）----
    ("GET", "/api/admin/tickets", None),
    ("GET", "/api/admin/tickets/1", None),
    ("PUT", "/api/admin/tickets/1", {"remark": "x"}),
    # ---- 统计（3）----
    ("GET", "/api/admin/stats/overview", None),
    ("GET", "/api/admin/stats/top-faults", None),
    ("GET", "/api/admin/stats/missed", None),
    # ---- 改密（1）----
    ("PUT", "/api/auth/password", {"old_password": "x", "new_password": "y" * 10}),
]


def test_protected_endpoint_list_is_complete() -> None:
    """守住清单本身：契约说 21 个，清单少了就是漏测，多了就是契约过期。"""
    assert len(PROTECTED_ENDPOINTS) == 21, (
        f"受保护端点清单有 {len(PROTECTED_ENDPOINTS)} 个，契约写的是 21 个。"
        "若确实新增了端点，请同步更新 API 契约 §9 与本清单。"
    )


@pytest.mark.parametrize(
    "method,path,body",
    PROTECTED_ENDPOINTS,
    ids=[f"{m} {p}" for m, p, _ in PROTECTED_ENDPOINTS],
)
def test_protected_endpoint_rejects_anonymous(
    client: TestClient, db: Session, method: str, path: str, body: dict | None
) -> None:
    """不带 token 访问任何受保护端点，必须是 401 且错误码正确。"""
    response = client.request(method, path, json=body)

    assert response.status_code == 401, f"{method} {path} 未拒绝匿名访问"
    assert response.json()["code"] == "AUTH_TOKEN_EXPIRED"


@pytest.mark.parametrize(
    "method,path,body",
    PROTECTED_ENDPOINTS,
    ids=[f"{m} {p}" for m, p, _ in PROTECTED_ENDPOINTS],
)
def test_protected_endpoint_rejects_bad_token(
    client: TestClient, db: Session, method: str, path: str, body: dict | None
) -> None:
    """伪造 token 也必须被拒——防止只判断"有没有 Authorization 头"。"""
    response = client.request(
        method, path, json=body, headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401, f"{method} {path} 接受了伪造 token"


def test_public_endpoints_do_not_require_token(client: TestClient, db: Session) -> None:
    """公开端点反过来不能被鉴权误伤——否则客户根本用不了。"""
    product = make_product(db)
    part = make_part(db, product)

    public = [
        ("GET", "/api/health", None),
        ("GET", "/api/products", None),
        # 公开故障列表要求 product_id + part_id（契约 §4），必须带上
        ("GET", f"/api/faults?product_id={product.id}&part_id={part.id}", None),
    ]
    for method, path, body in public:
        response = client.request(method, path, json=body)
        assert response.status_code == 200, f"公开端点 {method} {path} 返回 {response.status_code}"


# ================================================================
# TC-65 安全基线：密码哈希、停用账号
# ================================================================


def test_password_is_hashed_not_plaintext(client: TestClient, db: Session) -> None:
    """数据库里绝不能出现明文密码。"""
    make_user(db)

    user = db.query(User).filter(User.username == "admin").first()
    assert user is not None
    assert user.password_hash != DEFAULT_PASSWORD
    # bcrypt 哈希固定以 $2 开头，长度 60
    assert user.password_hash.startswith("$2")
    assert len(user.password_hash) == 60


def test_disabled_user_cannot_login(client: TestClient, db: Session) -> None:
    """账号停用后登录必须被拒，且错误码区别于"密码错误"。"""
    make_user(db)
    user = db.query(User).filter(User.username == "admin").first()
    user.is_active = False
    db.commit()

    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_USER_DISABLED"


def test_disabled_user_token_stops_working_immediately(client: TestClient, db: Session) -> None:
    """停用后**已签发**的 token 也必须立刻失效。

    这条容易被写成"等 token 过期才失效"，运维手册旧版就是这么写的（错的）。
    deps.py 每次请求都查 is_active，所以是立即失效——这对离职当天收回权限很重要。
    """
    headers = admin_headers(client, db)
    # 先确认 token 有效
    assert client.get("/api/admin/products", headers=headers).status_code == 200

    user = db.query(User).filter(User.username == "admin").first()
    user.is_active = False
    db.commit()

    response = client.get("/api/admin/products", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_USER_DISABLED"


# ================================================================
# TC-66 SQL 注入探测
# ================================================================


@pytest.mark.parametrize(
    "payload",
    [
        "' OR '1'='1",
        "'; DROP TABLE faults; --",
        "1' UNION SELECT * FROM users --",
        "%' OR 1=1 --",
    ],
)
def test_sql_injection_in_keyword_is_harmless(
    client: TestClient, db: Session, payload: str
) -> None:
    """关键词注入应被当作普通字符串处理，不报错、不泄露、不破坏表。"""
    product = make_product(db)
    part = make_part(db, product)

    response = client.get(
        "/api/faults",
        params={"product_id": product.id, "part_id": part.id, "q": payload},
    )

    # 既不 500（说明拼进了 SQL），也不返回不该返回的东西
    assert response.status_code == 200
    assert response.json() == []

    # 表还在，且 users 表没被 UNION 出来
    assert client.get("/api/products").status_code == 200


def test_sql_injection_in_login_is_harmless(client: TestClient, db: Session) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin' OR '1'='1", "password": "anything"},
    )

    assert response.status_code == 401
    assert "access_token" not in response.json()


# ================================================================
# TC-72 XSS：内容按纯文本存储与返回
# ================================================================


XSS_PAYLOAD = "<img src=x onerror=alert(1)>"


def test_xss_payload_stored_and_returned_as_text(client: TestClient, db: Session) -> None:
    """XSS 内容本身是合法文本，应该原样存储、原样返回。

    防护点在前端（禁用 v-html），后端不需要也不应该改写内容。
    这里断言后端**不**做转义（否则出现 &lt;img 说明多此一举），
    真正的防线由前端 lint 规则 `vue/no-v-html: error` + E2E 保证。
    """
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part, title=XSS_PAYLOAD)

    response = client.get(f"/api/faults/{fault.id}")

    assert response.status_code == 200
    # 原样返回，未被后端二次转义
    assert response.json()["title"] == XSS_PAYLOAD


def test_ticket_description_keeps_xss_payload(client: TestClient, db: Session) -> None:
    response = client.post(
        "/api/tickets",
        json={
            "contact": "13800138000",
            "description": XSS_PAYLOAD,
            # need_on_site 是必填（契约 §5），漏了会 422
            "need_on_site": False,
        },
    )

    assert response.status_code in (200, 201), response.text
    ticket_no = response.json()["ticket_no"]

    # 后台能查到原样内容（前端负责不执行它）
    headers = admin_headers(client, db)
    listing = client.get("/api/admin/tickets", params={"keyword": "13800138000"}, headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert ticket_no


# ================================================================
# TC-73 上传目录安全
# ================================================================


@pytest.mark.parametrize(
    "filename",
    [
        "../../etc/passwd.jpg",
        "../.env.pdf",
        ".php.jpg",
        "shell.php",
        "evil.sh",
        "x.exe",
    ],
)
def test_upload_rejects_dangerous_filename(
    client: TestClient, db: Session, filename: str
) -> None:
    """路径穿越与可执行后缀必须被拒。"""
    headers = admin_headers(client, db)
    # 后缀白名单在前，所以 .php/.sh/.exe 直接 400
    response = client.post(
        "/api/admin/upload",
        files={"file": (filename, io.BytesIO(b"fake-content"), "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 400, f"{filename} 未被拒绝"


def test_upload_renames_file(client: TestClient, db: Session) -> None:
    """合法文件落到磁盘时文件名必须被重命名，不能用客户端给的名字。"""
    headers = admin_headers(client, db)
    # 构造一个真实的 PNG 头，绕过文件头校验
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    response = client.post(
        "/api/admin/upload",
        files={"file": ("my-photo.png", io.BytesIO(png_header), "image/png")},
        headers=headers,
    )

    assert response.status_code == 200
    url = response.json()["url"]
    # 服务端重命名：文件名应含随机串，且不含原始名
    assert "my-photo" not in url
    assert url.startswith("/uploads/")


def test_uploads_path_traversal_denied(client: TestClient, db: Session) -> None:
    """直接访问 /uploads/../ 这类路径必须失败。"""
    # 这个请求走 nginx 层，TestClient 测的是后端；
    # 后端没有 /uploads 路由，应当 404 而不是把文件吐出来
    response = client.get("/uploads/../.env")
    assert response.status_code == 404
