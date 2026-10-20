"""文件上传：后缀白名单 + 文件头签名双校验、随机重命名（契约 §4）。

实现要点：
- **流式落盘**，不在内存里攒整个文件：20MB 上限 + 512MB 容器内存，几个并发就能顶爆；
- 先写 `.part` 临时文件，校验通过再改名，任何失败都清理临时文件；
- 落盘名随机生成，不使用客户端文件名（防路径穿越与覆盖）。
"""

from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings
from app.core.exceptions import BusinessError

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


async def save_upload(file: UploadFile) -> dict[str, object]:
    settings = get_settings()

    original_name = _safe_original_name(file.filename)
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        await file.close()
        raise BusinessError("UPLOAD_TYPE_NOT_ALLOWED", "不支持的文件类型", 400)

    limit = settings.max_upload_mb * 1024 * 1024
    target_dir = Path(settings.upload_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{datetime.now(settings.timezone):%Y%m%d}-{secrets.token_hex(4)}{ext}"
    target = target_dir / stored_name
    temp = target_dir / f".{stored_name}.part"

    written = 0
    head = b""
    header_checked = False

    try:
        with temp.open("wb") as out:
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
        temp.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    return {
        "url": f"/uploads/{stored_name}",
        "filename": original_name,
        "size": written,
    }
