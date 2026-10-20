#!/usr/bin/env python3
"""文档内路径引用检查器。

扫描所有 Markdown 中的反引号路径（如 `docs/02-技术设计/API接口契约.md`、
`deploy/schema.sql`），验证目标文件真实存在。支持两种解析基准：
  1) 仓库根相对
  2) 当前文件所在目录相对

用法：
    python scripts/dev/check_links.py [--quiet]

退出码：0 全部可解析；1 存在无法解析的引用。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SKIP_DIRS = {".git", "node_modules", ".venv", ".tmp", ".pipcache", ".npmcache", "data", "__pycache__"}
FILE_EXT = r"(?:md|sql|ya?ml|py|sh|mjs|conf|json|html|txt)"

ALLOWLIST_FILE = ROOT / "scripts" / "dev" / "link_allowlist.txt"

INLINE_CODE = re.compile(r"`([^`\n]+)`")
PATH_TOKEN = re.compile(rf"^[\w\u4e00-\u9fa5][\w\u4e00-\u9fa5./\-]*\.{FILE_EXT}$")


def iter_markdown() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        out.append(p)
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="只打印汇总")
    args = ap.parse_args()

    problems = []
    checked = 0

    allow = set()
    if ALLOWLIST_FILE.exists():
        for line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                allow.add(line)

    for md in iter_markdown():
        text = md.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            for span in INLINE_CODE.findall(line):
                token = span.strip()
                if not PATH_TOKEN.match(token):
                    continue
                if token.startswith(("http://", "https://")):
                    continue
                checked += 1
                is_md = token.endswith(".md")
                has_dir = "/" in token

                # 裸文件名且非 .md（如 `schema.sql`、`health.py`）多为行文简写，不校验
                if not is_md and not has_dir:
                    continue

                if token in allow:
                    continue

                if (ROOT / token).exists() or (md.parent / token).exists():
                    continue
                if not has_dir and next(ROOT.rglob(token), None) is not None:
                    continue
                problems.append((md.relative_to(ROOT), lineno, token))

    if problems and not args.quiet:
        print("无法解析的路径引用：")
        for f, ln, tok in problems:
            print(f"  {f}:{ln}  ->  {tok}")

    print(f"\n检查 {checked} 个引用，{len(problems)} 个无法解析")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
