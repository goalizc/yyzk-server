#!/usr/bin/env python3
"""前端硬编码中文文案检查。

目的：把「新增功能必须支持国际化」变成可执行的检查，而不是靠人记。

规则：
- 只扫 `frontend/src` 下的 `.vue` / `.js`（跳过 `locales/`、`*.spec.js`、`test-setup.js`）
- 注释、`<style>` 块不算（它们不面向用户）
- 代码里出现中文即视为违规 —— 文案必须进 `src/locales/*/`
- 确实需要保留中文的（如与后端约定的值），在该行加 `i18n-ignore` 标记并写明原因

用法：
    python scripts/dev/check_i18n.py          # 检查，有违规则退出码 1
    python scripts/dev/check_i18n.py -v       # 同时打印通过的文件数
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"

SKIP_DIRS = {"locales"}
SKIP_FILES = {"test-setup.js"}
CHINESE = re.compile(r"[\u4e00-\u9fff]")

STYLE_BLOCK = re.compile(r"<style[\s\S]*?</style>")
HTML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
# 行内注释：前面不是 http:// 或 https://
LINE_COMMENT = re.compile(r"(?<![:/])//.*$")


def _keep_newlines(match: re.Match) -> str:
    """删除片段但保留其中的换行数。

    直接用 re.sub("", ...) 会把换行一起吞掉，后面所有行的行号整体前移，
    报出的 `文件:行号` 指不到真实位置。这里只清空非换行字符。
    """
    return "\n" * match.group(0).count("\n")


def clean(source: str) -> str:
    """去掉不面向用户的片段，只留下可能产生界面文案的代码。"""
    source = STYLE_BLOCK.sub(_keep_newlines, source)
    source = HTML_COMMENT.sub(_keep_newlines, source)
    source = BLOCK_COMMENT.sub(_keep_newlines, source)
    return source


def scan_file(path: Path) -> list[tuple[int, str]]:
    text = clean(path.read_text(encoding="utf-8"))
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if "i18n-ignore" in line:
            continue
        # 去掉行尾注释后再判断；注释里的中文不算违规
        code = LINE_COMMENT.sub("", line)
        if CHINESE.search(code):
            hits.append((lineno, line.strip()[:120]))
    return hits


def iter_sources():
    for path in sorted(SRC.rglob("*")):
        if not path.is_file() or path.suffix not in {".vue", ".js"}:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILES or path.name.endswith(".spec.js"):
            continue
        yield path


def main() -> int:
    verbose = "-v" in sys.argv
    problems: list[tuple[Path, int, str]] = []
    scanned = 0

    for path in iter_sources():
        scanned += 1
        for lineno, line in scan_file(path):
            problems.append((path, lineno, line))

    if problems:
        print(f"发现 {len(problems)} 处硬编码中文（应移入 src/locales/）：\n")
        for path, lineno, line in problems:
            rel = path.relative_to(ROOT)
            print(f"  {rel}:{lineno}  {line}")
        print(
            "\n处理方式：\n"
            "  1. 把文案移到 frontend/src/locales/{zh-CN,en-US}/ 对应模块，组件里用 $t() / t()\n"
            "  2. 确实不能翻译的（与后端约定的比较值等），在该行加 `i18n-ignore` 注释并说明原因"
        )
        return 1

    if verbose:
        print(f"检查 {scanned} 个文件，未发现硬编码中文")
    else:
        print(f"国际化检查通过（{scanned} 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
