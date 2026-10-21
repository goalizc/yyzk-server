"""文件上传：后缀白名单 + 文件头（MIME）双校验、重命名、大小限制（契约 §4）。"""

from __future__ import annotations

import os
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


# ------------------------------------------------ 上传目录不可写（真实线上故障）
#
# 故障现场：POST /api/admin/upload 返回 500，堆栈末尾是
#   PermissionError: [Errno 13] Permission denied: '/data/uploads/.xxx.png.part'
# 原因：upload_dir 是宿主机目录挂载，镜像里构建的属主被挂载点覆盖，
# 运维漏 chown 时目录属主是 root，容器以 uid 10001 运行就写不进去。
#
# 这些用例锁住两条行为：
#   1. 目录不可写但父目录可写时，自愈（删掉重建）后上传照常成功；
#   2. 彻底不可写时返回 503 + SERVICE_UNAVAILABLE，而不是 500 + INTERNAL_ERROR。


def test_ensure_upload_dir_leaves_unwritable_dir_untouched(monkeypatch, tmp_path) -> None:
    """目录不可写时**不动目录内容**，留给运维处理。

    这条用例锁住一个设计取舍：早期版本尝试 rename/rmdir 自愈，
    结果在挂载点上全部 `Device or resource busy`，且异常被吞掉表现为静默失败。
    更关键的是——目录里可能挂着 20 个正常附件，删内容是不可接受的。
    """
    from app.utils import upload as upload_mod

    target = tmp_path / "uploads"
    target.mkdir()
    keep = target / "important.pdf"
    keep.write_bytes(b"%PDF-1.4 keep me")

    real_access = os.access

    def fake_access(path, mode, **kwargs):
        if str(path) == str(target) and mode == os.W_OK:
            return False
        return real_access(path, mode, **kwargs)

    monkeypatch.setattr(upload_mod.os, "access", fake_access)

    result = upload_mod.ensure_upload_dir(target)

    # 返回原目录，不抛异常（由调用方决定报什么错）
    assert result == target
    # 关键：原有文件一个都没动
    assert keep.exists()
    assert keep.read_bytes() == b"%PDF-1.4 keep me"


def test_ensure_upload_dir_creates_missing(tmp_path) -> None:
    """目录不存在时自动创建（首次部署的常见状态）。"""
    from app.utils.upload import ensure_upload_dir

    target = tmp_path / "a" / "b" / "uploads"
    assert not target.exists()

    result = ensure_upload_dir(target)

    assert result.is_dir()
    assert os.access(result, os.W_OK)


def test_upload_returns_503_when_dir_unrecoverable(client: TestClient, db, monkeypatch, tmp_path) -> None:
    """目录不可写 → 503 + SERVICE_UNAVAILABLE，而不是 500 + INTERNAL_ERROR。

    这是本次线上故障的直接回归用例：改造前这里返回 500 + INTERNAL_ERROR，
    用户只看到"服务器内部错误"，运维无法从错误码判断是权限问题。

    不用 chmod 来构造场景：测试在 CI/容器里常以 root 运行，root 无视权限位，
    用例会退化成"永远通过"。改为直接让 open() 抛 PermissionError，
    精确复现故障那一行（`with temp.open("wb")`）。
    """
    target = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", target)

    real_open = Path.open

    def fake_open(self, *args, **kwargs):
        if self.suffix == ".part":
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)

    headers = admin_headers(client, db)
    response = client.post(
        "/api/admin/upload", files={"file": ("a.jpg", JPEG, "image/jpeg")}, headers=headers
    )

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert body["code"] != "INTERNAL_ERROR"
    # 不泄漏服务器路径
    assert str(target) not in body["detail"]


# ---------------------------------------------------------------- 删除与回收


def _upload(client: TestClient, headers: dict) -> str:
    """上传一张图，返回 url。"""
    response = client.post(
        "/api/admin/upload", files={"file": ("a.png", PNG, "image/png")}, headers=headers
    )
    assert response.status_code == 200
    return response.json()["url"]


def test_delete_upload_removes_file(client: TestClient, db, tmp_path, monkeypatch) -> None:
    """正常的"上传后移除"：文件必须从磁盘消失。

    这是本次修复的核心回归用例。改造前前端只清空表单值、不通知后端，
    文件永久残留——用户报障时磁盘上就躺着一张测试图。
    """
    target = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", target)

    headers = admin_headers(client, db)
    url = _upload(client, headers)
    stored = target / url.rsplit("/", 1)[-1]
    assert stored.is_file()

    response = client.delete(f"/api/admin/upload?url={url}", headers=headers)

    assert response.status_code == 200
    assert not stored.exists(), "点移除后文件应被删除"


def test_delete_upload_is_idempotent(client: TestClient, db, tmp_path, monkeypatch) -> None:
    """文件已不存在时返回 200，不报 404。

    两个标签页同时点移除、或清理任务刚跑过，都会命中这个场景。
    报 404 会让用户看到一个毫无意义的错误提示。
    """
    target = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", target)

    headers = admin_headers(client, db)
    missing = "/uploads/20260101-deadbeef.png"

    response = client.delete(f"/api/admin/upload?url={missing}", headers=headers)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "bad_url",
    [
        "/uploads/../../app/main.py",
        "/uploads/../../deploy/.env",
        "/uploads/20261021-0b3f9a7c.exe",
        "/uploads/etc/passwd",
        "/uploads/20261021-0b3f9a7c.png/../../x.png",
    ],
)
def test_delete_upload_rejects_path_traversal(
    client: TestClient, db, bad_url: str
) -> None:
    """不能让删除接口变成"任意文件删除器"。

    文件名必须严格匹配 save_upload 的生成格式，任何不合格式的输入直接 400。
    """
    headers = admin_headers(client, db)

    response = client.delete(f"/api/admin/upload?url={bad_url}", headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_delete_upload_refuses_referenced_file(
    client: TestClient, db, tmp_path, monkeypatch
) -> None:
    """仍被故障方案引用的文件不能删。

    同一张图可能被复用到多条方案里。删了之后另一条方案显示破图，
    而且没有任何提示——这种静默损坏比多占几 MB 磁盘严重得多。
    """
    from app.models import Fault, Part, Product

    target = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", target)

    headers = admin_headers(client, db)
    url = _upload(client, headers)
    stored = target / url.rsplit("/", 1)[-1]

    # 造一条引用该图的故障
    product = Product(name="扫地机", model="X1", is_active=True, sort_order=0)
    db.add(product)
    db.flush()
    part = Part(name="电池", product_id=product.id, sort_order=0)
    db.add(part)
    db.flush()
    db.add(
        Fault(
            product_id=product.id,
            part_id=part.id,
            title="电池不充电",
            symptom="不充电",
            root_cause="电池老化",
            solution_steps=[{"step": 1, "text": "更换电池", "image_url": url}],
            attachment_urls=[],
            is_published=True,
        )
    )
    db.commit()

    response = client.delete(f"/api/admin/upload?url={url}", headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "UPLOAD_IN_USE"
    assert stored.exists(), "被引用的文件必须留着"


def test_sweep_dry_run_does_not_delete(client: TestClient, db, tmp_path, monkeypatch) -> None:
    """dry-run 只报告，不动文件。默认值必须是 dry-run。"""
    from app.services.upload_cleanup import sweep

    target = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", target)

    orphan = target / "20250101-aaaaaaaa.png"
    orphan.write_bytes(b"x" * 10)
    old = 1700000000  # 远早于 min_age
    os.utime(orphan, (old, old))

    result = sweep(db, apply=False, min_age_minutes=60)

    assert result.candidates == [orphan.name]
    assert result.deleted == []
    assert result.dry_run is True
    assert orphan.exists(), "dry-run 不允许删任何文件"


def test_sweep_skips_recent_files(db, tmp_path, monkeypatch) -> None:
    """刚上传的文件不能被动——用户可能正在填表还没保存。

    这是最危险的误删场景：清理任务恰好在"上传完成、保存之前"运行，
    用户点保存时图片 404。
    """
    from app.services.upload_cleanup import sweep

    target = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", target)

    fresh = target / "20250101-bbbbbbbb.png"
    fresh.write_bytes(b"x" * 10)  # mtime = 现在

    result = sweep(db, apply=True, min_age_minutes=60)

    assert result.deleted == []
    assert result.skipped_too_new == 1
    assert fresh.exists()


def test_sweep_reclaims_orphan(db, tmp_path, monkeypatch) -> None:
    """够老且无人引用的文件应被回收，并统计释放空间。"""
    from app.services.upload_cleanup import sweep

    target = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", target)

    orphan = target / "20250101-cccccccc.png"
    orphan.write_bytes(b"x" * 100)
    old = 1700000000
    os.utime(orphan, (old, old))

    result = sweep(db, apply=True, min_age_minutes=60)

    assert result.deleted == [orphan.name]
    assert result.freed_bytes == 100
    assert not orphan.exists()


def test_sweep_refuses_when_ratio_too_high(db, tmp_path, monkeypatch) -> None:
    """待删比例过高说明引用扫描可能失效，必须拒绝执行而不是照删。

    宁可漏删，也不能因为一次 bug 把库里的图删掉一半。
    注意闸门只在目录达到 RATIO_GATE_MIN_FILES（10）时生效，
    所以这里要造够 10 个文件才能测到闸门本身。
    """
    from app.services.upload_cleanup import RATIO_GATE_MIN_FILES, sweep

    target = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", target)

    for i in range(RATIO_GATE_MIN_FILES):
        f = target / f"20250101-{i:08x}.png"
        f.write_bytes(b"x" * 10)
        os.utime(f, (1700000000, 1700000000))

    result = sweep(db, apply=True, min_age_minutes=60, max_ratio=0.5)

    assert result.refused is True
    assert result.deleted == []
    assert "超过比例上限" in result.reason
    assert len(list(target.iterdir())) == RATIO_GATE_MIN_FILES, "拒绝执行时一个文件都不能删"


def test_sweep_small_dir_not_blocked_by_ratio(db, tmp_path, monkeypatch) -> None:
    """小目录不触发比例闸门，否则运维最需要的场景永远清不了。

    真实故障：第一次实现时无条件按比例判定，目录里只有 1 个孤儿文件时
    比例是 100%，直接被拒绝执行——单文件残留恰恰是最常见的清理场景。
    """
    from app.services.upload_cleanup import sweep

    target = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", target)

    orphan = target / "20250101-cccccccc.png"
    orphan.write_bytes(b"x" * 10)
    os.utime(orphan, (1700000000, 1700000000))

    result = sweep(db, apply=True, min_age_minutes=60, max_ratio=0.5)

    assert result.refused is False
    assert result.deleted == [orphan.name]


def test_sweep_ignores_dot_files_and_parts(db, tmp_path, monkeypatch) -> None:
    """.gitkeep 与写了一半的 .part 不能被当垃圾回收。

    .part 可能正被另一个上传请求写入，删掉会让那个请求失败。
    """
    from app.services.upload_cleanup import sweep

    target = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", target)

    keep = target / ".gitkeep"
    keep.write_text("")
    part = target / ".20250101-dddddddd.png.part"
    part.write_bytes(b"x")

    result = sweep(db, apply=True, min_age_minutes=0)

    assert result.total_files == 0
    assert keep.exists()
    assert part.exists()
