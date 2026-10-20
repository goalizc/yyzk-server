"""文件上传：后缀白名单 + 文件头（MIME）双校验、重命名、大小限制（契约 §4）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.conftest import auth_headers, login, make_user

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
PDF = b"%PDF-1.4\n" + b"0" * 200
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 200


def admin_headers(client: TestClient, db) -> dict:
    make_user(db)
    return auth_headers(login(client)["access_token"])


def test_upload_requires_token(client: TestClient, db) -> None:
    response = client.post("/api/admin/upload", files={"file": ("a.jpg", JPEG, "image/jpeg")})

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("filename", "content", "expected_ext"),
    [("photo.jpg", JPEG, ".jpg"), ("photo.png", PNG, ".png"), ("手册.pdf", PDF, ".pdf"),
     ("clip.mp4", MP4, ".mp4")],
)
def test_upload_accepts_whitelisted_types(
    client: TestClient, db, filename: str, content: bytes, expected_ext: str
) -> None:
    headers = admin_headers(client, db)

    response = client.post(
        "/api/admin/upload", files={"file": (filename, content, "application/octet-stream")}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["url"].startswith("/uploads/")
    assert body["url"].endswith(expected_ext)
    assert body["filename"] == filename  # 返回原文件名，但落盘名是随机的
    assert body["size"] == len(content)

    stored = Path(get_settings().upload_dir) / Path(body["url"]).name
    assert stored.exists()
    assert stored.read_bytes() == content


def test_upload_replaces_name_with_random(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    first = client.post("/api/admin/upload", files={"file": ("../../etc/passwd.jpg", JPEG, "image/jpeg")}, headers=headers)
    second = client.post("/api/admin/upload", files={"file": ("../../etc/passwd.jpg", JPEG, "image/jpeg")}, headers=headers)

    assert first.status_code == 200
    name1 = Path(first.json()["url"]).name
    name2 = Path(second.json()["url"]).name
    assert name1 != name2  # 随机名，不保留原名、不带路径
    assert "passwd" not in name1 and "/" not in name1


def test_upload_rejects_bad_extension(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.post("/api/admin/upload", files={"file": ("evil.exe", JPEG, "image/jpeg")}, headers=headers)

    assert response.status_code == 400
    assert response.json() == {"detail": "不支持的文件类型", "code": "UPLOAD_TYPE_NOT_ALLOWED"}


def test_upload_rejects_content_mismatch(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    # 后缀是 .jpg，内容是 PDF —— 只校验后缀的实现会漏过
    response = client.post("/api/admin/upload", files={"file": ("fake.jpg", PDF, "image/jpeg")}, headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] == "UPLOAD_TYPE_NOT_ALLOWED"


def test_upload_rejects_oversize(client: TestClient, db, monkeypatch) -> None:
    headers = admin_headers(client, db)
    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    big = JPEG + b"0" * (1024 * 1024)
    response = client.post("/api/admin/upload", files={"file": ("big.jpg", big, "image/jpeg")}, headers=headers)

    assert response.status_code == 413
    body = response.json()
    assert body["code"] == "UPLOAD_TOO_LARGE"
    assert "限制" in body["detail"]


def test_upload_empty_file_rejected(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.post("/api/admin/upload", files={"file": ("empty.jpg", b"", "image/jpeg")}, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "文件内容为空"


def test_oversize_rejection_leaves_no_temp_file(client: TestClient, db, monkeypatch) -> None:
    headers = admin_headers(client, db)
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)

    client.post(
        "/api/admin/upload",
        files={"file": ("big.jpg", JPEG + b"0" * (1024 * 1024), "image/jpeg")},
        headers=headers,
    )

    leftovers = [p for p in Path(get_settings().upload_dir).glob("*.part")]
    assert leftovers == []
