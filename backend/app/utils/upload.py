"""文件上传：后缀白名单 + 文件头签名双校验、随机重命名（契约 §4）。

实现要点：
- **流式落盘**，不在内存里攒整个文件：20MB 上限 + 512MB 容器内存，几个并发就能顶爆；
- 先写 `.part` 临时文件，校验通过再改名，任何失败都清理临时文件；
- 落盘名随机生成，不使用客户端文件名（防路径穿越与覆盖）。
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings
from app.core.exceptions import BusinessError

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".mp4"}

CHUNK_SIZE = 1024 * 1024  # 1MB
HEADER_SIZE = 16

# 第二道校验：不信任客户端给的 Content-Type，直接看文件头
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".pdf": (b"%PDF-",),
}


def _content_matches(ext: str, head: bytes) -> bool:
    if ext == ".mp4":
        # ISO BMFF：第 5–8 字节为 ftyp
        return len(head) >= 8 and head[4:8] == b"ftyp"
    return any(head.startswith(signature) for signature in _SIGNATURES[ext])


def _safe_original_name(filename: str | None) -> str:
    # 只取末段文件名，路径一律丢弃（防路径穿越）
    return Path(filename or "").name or "upload"


def ensure_upload_dir(target_dir: Path) -> Path:
    """确保上传目录存在且可写，必要时尝试自愈。

    为什么需要这一步：`upload_dir` 在 compose 里是**宿主机目录挂载**，
    镜像构建时的 chown 会被挂载点覆盖，最终属主取决于宿主机上那个目录
    是谁建的。运维漏了 `chown -R 10001:10001 data/uploads`，上传就会挂在
    `PermissionError: [Errno 13]` 上——这是本项目的真实线上故障。

    **应用层救不了这个故障，只能把它变干净**，原因有三：
      1. 挂载点是 busy 的，`rename`/`rmdir` 一律 `Device or resource busy`；
      2. 目录内容即使删光，目录自身的 mode 仍是 555，还是写不进去；
      3. 改 mode/属主需要 root，容器以非 root 运行（且不该为这个降权）。

    所以这里的自愈只覆盖"目录不存在 / 存在且可写"这类正常情况；
    真正不可写时**不在应用层乱动文件**（挂了 20 个附件时删内容是不可接受的），
    直接交给调用方报 503，由运维按错误码执行 `prepare-storage.sh` 修权限。

    Returns:
        目标目录。调用方负责处理"仍然不可写"的情况。
    """
    if target_dir.is_dir() and os.access(target_dir, os.W_OK):
        return target_dir

    if target_dir.is_dir():
        # 目录在但不可写：什么都不做，保留现场交给运维。
        # 这里踩过坑——早期版本尝试 rename/rmdir 自愈，在挂载点上全部失败，
        # 且失败被 except OSError 吞掉，表现为"静默不生效"。
        logger.error(
            "上传目录不可写：%s（属主 %s）。请在宿主机执行 "
            "sudo ./scripts/prepare-storage.sh 修正权限后重启 backend",
            target_dir,
            _owner_of(target_dir),
        )
        return target_dir

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("上传目录创建失败：%s（%s）", target_dir, exc)

    return target_dir


def _owner_of(path: Path) -> str:
    """取属主 uid:gid，仅用于日志（运维需要知道该 chown 成什么）。"""
    try:
        stat = path.stat()
        return f"{stat.st_uid}:{stat.st_gid}"
    except OSError:
        return "unknown"


async def save_upload(file: UploadFile) -> dict[str, object]:
    settings = get_settings()

    original_name = _safe_original_name(file.filename)
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        await file.close()
        raise BusinessError("UPLOAD_TYPE_NOT_ALLOWED", "不支持的文件类型", 400)

    limit = settings.max_upload_mb * 1024 * 1024
    target_dir = ensure_upload_dir(Path(settings.upload_dir))
    stored_name = f"{datetime.now(settings.timezone):%Y%m%d}-{secrets.token_hex(4)}{ext}"
    target = target_dir / stored_name
    temp = target_dir / f".{stored_name}.part"

    written = 0
    head = b""
    header_checked = False

    try:
        try:
            out_file = temp.open("wb")
        except PermissionError as exc:
            # 目录不可写。这是部署问题不是程序缺陷，报 503 让运维按错误码
            # 去查权限；500 只会让人以为是代码 bug。
            await file.close()
            logger.error(
                "上传目录不可写：%s（%s）。请在宿主机执行 "
                "sudo ./scripts/prepare-storage.sh 后重启 backend",
                target_dir,
                exc,
            )
            raise BusinessError(
                "SERVICE_UNAVAILABLE",
                "服务器暂时无法保存文件，请联系管理员",
                503,
            ) from exc

        with out_file as out:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise BusinessError(
                        "UPLOAD_TOO_LARGE",
                        f"文件超过 {settings.max_upload_mb}MB 限制",
                        413,
                    )
                if len(head) < HEADER_SIZE:
                    head += chunk[: HEADER_SIZE - len(head)]
                # 头部凑够就先校验，别等整个文件写完
                if not header_checked and len(head) >= 12:
                    header_checked = True
                    if not _content_matches(ext, head):
                        raise BusinessError("UPLOAD_TYPE_NOT_ALLOWED", "不支持的文件类型", 400)
                out.write(chunk)

        if written == 0:
            raise BusinessError("VALIDATION_ERROR", "文件内容为空", 400)
        if not header_checked and not _content_matches(ext, head):
            raise BusinessError("UPLOAD_TYPE_NOT_ALLOWED", "不支持的文件类型", 400)

        temp.replace(target)
    except BaseException:
        # 清理尽力而为：目录不可写时 unlink 自己也会抛 PermissionError，
        # 那会把真正的错误（比如 413 / 类型不符）顶掉，用户看到的是权限问题。
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        await file.close()

    return {
        "url": f"/uploads/{stored_name}",
        "filename": original_name,
        "size": written,
    }
