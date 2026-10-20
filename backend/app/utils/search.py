"""搜索输入处理：把用户输入安全地转成 LIKE 模式。"""

from __future__ import annotations

LIKE_ESCAPE = "\\"


def like_pattern(value: str) -> str:
    """转义 LIKE 通配符，避免用户输入的 % 和 _ 被当成语法。

    调用方需传同样的 escape 字符：`.like(pattern, escape=LIKE_ESCAPE)`。
    """
    escaped = (
        value.strip()
        .replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"
