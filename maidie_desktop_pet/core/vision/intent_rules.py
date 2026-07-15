"""从用户显式措辞解析 Vision capture scope。

BrainRouter 使用这些规则区分活动窗口、全屏、鼠标附近和框选区域；规则只描述范围，
不执行截图，模糊请求仍由 Router 的澄清流程处理。
"""

from __future__ import annotations

import re
from enum import Enum


class VisionScope(str, Enum):
    """ScreenCapture 支持的显式截图范围。"""
    ACTIVE_WINDOW = "active_window"
    FULLSCREEN = "fullscreen"
    CURSOR_REGION = "cursor_region"
    SELECTED_REGION = "selected_region"


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
    r"(?:是?什么意思|怎么(?:弄|点|操作|办)|如何(?:操作|处理))?"
    r"[？?！!。.\s]*$", re.I,
)
_SELECTED_REGION = re.compile(
    r"框选|圈选|手动选|选择区域|选个区域|选一块|截一块|我选的|我框一个|"
    r"框一块|这个区域|region", re.I,
)
_FULLSCREEN = re.compile(
    r"全屏|整个屏幕|整块屏幕|整个桌面|整个界面|全部内容|看全部", re.I,
)
_ACTIVE_WINDOW = re.compile(
    r"当前窗口|这个窗口|当前界面|看(?:一下)?屏幕|现在屏幕|这个报错|"
    r"屏幕.*(?:题|报错)", re.I,
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
    """兼容旧调用方，返回检测到的 scope 字符串。"""
    return detect_vision_scope(text, default).value


def detect_vision_scope(user_text: str,
                        default_scope: str = "active_window") -> VisionScope:
    """按显式优先级解析 scope，未指明时使用经校验的默认值。"""
    value = str(user_text).strip()
    if _SELECTED_REGION.search(value):
        return VisionScope.SELECTED_REGION
    if _FULLSCREEN.search(value):
        return VisionScope.FULLSCREEN
    if is_cursor_region_request(value):
        return VisionScope.CURSOR_REGION
    if _ACTIVE_WINDOW.search(value):
        return VisionScope.ACTIVE_WINDOW
    try:
        scope = VisionScope(default_scope)
    except ValueError:
        scope = VisionScope.ACTIVE_WINDOW
    return VisionScope.ACTIVE_WINDOW if scope is VisionScope.SELECTED_REGION else scope


def is_explicit_scope_request(text: str) -> bool:
    """判断请求是否足以跳过 Vision scope 澄清。"""
    value = str(text).strip()
    return bool(
        _SELECTED_REGION.search(value)
        or _FULLSCREEN.search(value)
        or is_cursor_region_request(value)
        or _ACTIVE_WINDOW.search(value)
    )
