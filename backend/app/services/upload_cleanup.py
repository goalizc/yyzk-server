"""上传文件回收：识别并清理无人引用的残留文件。

## 为什么需要这个模块

上传与删除是**两个独立动作**：
  - 上传落盘发生在 `POST /api/admin/upload`，文件立即写到 `/data/uploads`；
  - 业务引用发生在 `PUT /api/admin/faults/{id}` 保存时，URL 写进
    `faults.solution_steps` / `faults.attachment_urls` 两个 JSONB 字段。

两者之间只要用户没走完保存，文件就成了孤儿。真实场景至少四类：
  1. 上传后点了"移除"——前端原本只清空表单值，**从不通知后端**（本次修复前）；
  2. 上传后直接关闭页面 / 关浏览器；
  3. 编辑时换了一张图，旧图 URL 从 JSONB 里被覆盖；
  4. 保存时校验失败，整个表单没提交。

**第 3、4 类无法用"主动删除"解决**，因为后端根本不知道旧图被替换了
（前端只提交新数组，后端无从判断哪个是有意替换、哪个是手滑）。
所以必须有一条兜底链路：定期把"磁盘上有、库里没人引用"的文件清掉。

## 引用判定的口径（重要）

引用关系藏在 JSONB 里，没有独立的附件表，因此**只能扫全表比对文件名**：

- 取 `faults.solution_steps` 里每个元素的 `image_url`
- 取 `faults.attachment_urls` 里每个元素的 `url`
- 两者形如 `/uploads/20261021-0d0f4f0e.png`，取 basename 作为集合元素

不用 LIKE 拼 SQL 的原因：文件名是 16 进制随机串，`%` 通配在 JSONB 上无法走索引，
且要防 `_` 被当通配符；全表取两个 JSONB 字段在万级数据量下只需百毫秒。
当前 `faults` 是知识库表，规模在千级，这个做法足够；真正到十万级再考虑
建 `upload_files` 引用表。

## 安全护栏

清理是不可逆操作，所以有三重保护：

1. **默认 dry-run**：不传 `apply=True` 只返回将要删什么，不动文件；
2. **年龄下限**：只删 mtime 早于 `min_age_minutes` 的文件（默认 60 分钟）。
   否则会误删"刚上传、还没保存"的文件——这是最危险的误删场景：
   用户上传后正在填写内容，清理任务恰好在此时运行，用户保存时就 404 了；
3. **比例闸门**：如果待删文件占总数超过 `max_ratio`（默认 0.5），
   判定为"引用扫描出了问题"（比如表名改错、JSONB 结构变了），直接拒绝执行。
   宁可漏删，也不能一次删掉一半库里的图。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Fault

logger = logging.getLogger(__name__)

# 只回收本系统约定的上传目录内的文件；文件名由 save_upload 生成，
# 形如 20261021-0d0f4f0e.png（日期-8位随机-扩展名）
DEFAULT_MIN_AGE_MINUTES = 60
DEFAULT_MAX_RATIO = 0.5

# 比例闸门只在目录达到这个规模时才生效。
# 原因：小目录下比例没有统计意义。目录里只有 1 个孤儿文件时比例是 100%，
# 若一律拦截，运维最需要清理的场景反而永远清不了。
# 闸门防的是"引用扫描失效导致批量误删"，那必然是规模化的现象。
RATIO_GATE_MIN_FILES = 10


@dataclass
class SweepResult:
    """一次清理的结果。dry_run=True 时 deleted 为空，candidates 是"将删"。"""

    total_files: int = 0
    referenced: int = 0
    candidates: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    freed_bytes: int = 0
    dry_run: bool = True
    # 被跳过（太新）的文件数，供运维判断"是不是刚上传的还没保存"
    skipped_too_new: int = 0
    # 触发比例闸门时为 True，此时的 candidates 仅供查看、未删任何东西
    refused: bool = False
    reason: str = ""


def _referenced_names(db: Session) -> set[str]:
    """库里所有被引用的文件名（不含 `/uploads/` 前缀）。

    两条来源：
      - solution_steps[].image_url
      - attachment_urls[].url
    值为空/为 None 的元素跳过——历史数据里可能有 `{"step":1,"text":"..."}`
    这种没有图的步骤。
    """
    names: set[str] = set()

    rows = db.execute(select(Fault.solution_steps, Fault.attachment_urls)).all()
    for steps, attachments in rows:
        for item in steps or []:
            if not isinstance(item, dict):
                continue
            url = item.get("image_url")
            if url:
                names.add(os.path.basename(url))
        for item in attachments or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if url:
                names.add(os.path.basename(url))

    return names


def _list_upload_files(upload_dir: Path) -> list[Path]:
    """列出上传目录里的普通文件，跳过临时文件与占位文件。

    `.part` 是 save_upload 写到一半的临时文件，`.gitkeep` 用于保留空目录，
    两者都不该被回收器当垃圾处理（`.part` 可能正在被另一个请求写入）。
    """
    if not upload_dir.is_dir():
        return []

    out: list[Path] = []
    for entry in upload_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            continue
        out.append(entry)
    return out


def sweep(
    db: Session,
    *,
    apply: bool = False,
    min_age_minutes: int = DEFAULT_MIN_AGE_MINUTES,
    max_ratio: float = DEFAULT_MAX_RATIO,
) -> SweepResult:
    """扫描并清理孤儿文件。

    Args:
        db: 用于读取引用关系的会话。
        apply: False（默认）只报告不删除。**必须显式传 True 才会真删**。
        min_age_minutes: 只处理 mtime 早于该分钟数的文件，保护"刚上传未保存"。
        max_ratio: 待删比例上限，超过则拒绝执行。

    Returns:
        SweepResult。refused=True 时未删除任何文件，reason 说明原因。
    """
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)

    result = SweepResult(dry_run=not apply)

    files = _list_upload_files(upload_dir)
    result.total_files = len(files)
    if not files:
        result.reason = "上传目录为空或不存在"
        return result

    referenced = _referenced_names(db)
    result.referenced = len(referenced)

    now = time.time()
    min_age_seconds = min_age_minutes * 60
    candidates: list[Path] = []

    for path in files:
        if path.name in referenced:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError as exc:
            # 文件刚被别人删了，或者没权限 stat——跳过，不要因为它中断整轮清理
            logger.warning("跳过无法 stat 的文件 %s：%s", path.name, exc)
            continue

        if now - mtime < min_age_seconds:
            result.skipped_too_new += 1
            continue

        candidates.append(path)

    result.candidates = sorted(p.name for p in candidates)

    # 比例闸门：待删过半说明引用扫描大概率失效，宁可什么都不做。
    # 仅在目录有一定规模时生效——小目录比例无意义，见 RATIO_GATE_MIN_FILES。
    if (
        len(files) >= RATIO_GATE_MIN_FILES
        and len(candidates) / len(files) > max_ratio
    ):
        result.refused = True
        result.reason = (
            f"待删 {len(candidates)}/{len(files)} 个文件，超过比例上限 "
            f"{max_ratio:.0%}，疑似引用扫描异常，已拒绝执行。"
            f"请先用 dry-run 核对引用数（当前识别到 {len(referenced)} 个被引用文件名），"
            f"确认无误后调大 --max-ratio 再执行"
        )
        logger.error("上传目录清理被拒绝：%s", result.reason)
        return result

    if not apply:
        if not candidates:
            result.reason = "没有需要清理的文件"
        return result

    for path in candidates:
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError as exc:
            # 单个文件删不掉不影响其余文件；容器以非 root 运行，属主异常时常见
            logger.warning("删除失败 %s：%s", path.name, exc)
            continue
        result.deleted.append(path.name)
        result.freed_bytes += size

    if result.deleted:
        logger.info(
            "上传目录清理完成：删除 %d 个文件，释放 %.1f MB",
            len(result.deleted),
            result.freed_bytes / 1024 / 1024,
        )

    return result


def referenced_by_fault(db: Session, names: set[str]) -> set[str]:
    """判断给定文件名中，有哪些被任一故障引用。

    供删除接口使用：前端点"移除"时请求删某个文件，必须先确认它没被别的
    故障正在使用——同一张图被复制到两条方案里的情况虽然少见，但一旦删了，
    另一条方案就会显示破图，且没有任何提示。
    """
    if not names:
        return set()
    return names & _referenced_names(db)
