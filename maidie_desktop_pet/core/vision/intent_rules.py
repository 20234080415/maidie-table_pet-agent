from __future__ import annotations

import re


_CURSOR_REFERENCE = re.compile(r"鼠标|光标|指针|mouse|cursor", re.I)
_SPATIAL_REFERENCE = re.compile(
    r"指着|指向|所指|所在|附近|旁边|周围|下面|上面|位置|地方|区域|"
    r"这(?:里|边|块|一块|个)|那(?:里|边|块|一块|个)", re.I,
)
_VISUAL_TASK = re.compile(
    r"看|瞧|分析|识别|检查|帮|题|报错|错误|按钮|内容|界面|页面|窗口|"
    r"怎么|如何|什么|啥|意思|解决", re.I,
)
_DIRECT_CURSOR_DEIXIS = re.compile(
    r"^(?:(?:帮我|请|能)?(?:看+|瞧|分析|检查)(?:一下)?)?"
    r"(?:这里|这边|这块|这一块|这个位置|这个按钮)"
    r"[？?！!。.\s]*$", re.I,
)


def is_cursor_region_request(text: str) -> bool:
    """Recognize cursor-scoped requests compositionally, not by full sentences."""
    value = str(text).strip()
    if _DIRECT_CURSOR_DEIXIS.fullmatch(value):
        return True
    return bool(
        _CURSOR_REFERENCE.search(value)
        and _SPATIAL_REFERENCE.search(value)
        and _VISUAL_TASK.search(value)
    )


def vision_scope_for(text: str, default: str = "active_window") -> str:
    return "cursor_region" if is_cursor_region_request(text) else default
