from __future__ import annotations

import re
from typing import Any


TIME = re.compile(r"现在几点|今天几号|今天星期几|当前时间|现在时间|\b(?:time|date)\b", re.I)
WEATHER = re.compile(r"天气怎么样|今天天气|今天下雨吗|今天冷不冷|现在多少度|(?:长沙|深圳)天气", re.I)
SCREEN = re.compile(
    r"看屏幕|看一下屏幕|看看我屏幕|看看我的屏幕|你看看我现在|当前窗口|屏幕上|截图|"
    r"看图|图片里|这张图|这个报错|帮我看一下这个报错|帮我看一下屏幕|"
    r"你看看我现在屏幕这个题怎么写|你看看我现在屏幕这个报错|"
    r"你能.*(?:看到|看见).*(?:屏幕|桌面)", re.I,
)
AMBIGUOUS_VISION = re.compile(
    r"^(?:这个怎么弄|这是啥情况|帮我看看|帮我看一下|看一下|这个什么意思|这个题怎么写|这题怎么做)"
    r"[？?！!。.\s]*$", re.I,
)
CURSOR_VISION = re.compile(
    r"^(?:看这里|看鼠标这块|这个按钮|这个位置|这块)[？?！!。.\s]*$", re.I,
)
TECHNICAL = re.compile(r"代码|编译|linux|cmake|makefile|python|api|报错", re.I)
EXPLANATION = re.compile(r"是什么意思|怎么用|有什么作用", re.I)
GREETING = re.compile(r"^(?:你好|嗨|hello|hi|嗯|好的)[！!。.？?\s]*$", re.I)
SEARCH = re.compile(r"搜索|搜|继续查|帮我查|查一下|查询|search|look up", re.I)
COMPLEX_WEATHER = re.compile(r"适合|穿什么|安排|出去玩|建议|推荐|应该", re.I)


def is_simple_time_query(text: str) -> bool:
    return bool(TIME.search(str(text).strip()))


def is_weather_query(text: str) -> bool:
    return bool(WEATHER.search(str(text).strip()))


def is_simple_weather_query(text: str) -> bool:
    value = str(text).strip()
    return is_weather_query(value) and not bool(COMPLEX_WEATHER.search(value))


def fast_route(text: str) -> dict[str, Any] | None:
    value = str(text).strip()
    if CURSOR_VISION.search(value):
        return _route("vision", "explicit cursor-region request", need_screen=True,
                      need_vision=True, vision_scope="cursor_region")
    if AMBIGUOUS_VISION.fullmatch(value):
        return _route("clarification", "ambiguous visual reference", need_screen=False,
                      need_vision=False)
    if SCREEN.search(value):
        return _route("vision", "explicit screen request", need_screen=True, need_vision=True)
    if is_simple_time_query(value):
        return _route("task", "deterministic time query")
    if is_weather_query(value):
        return _route("task", "deterministic weather query")
    if SEARCH.search(value):
        return _route("task", "deterministic search request")
    if TECHNICAL.search(value) and EXPLANATION.search(value):
        return _route("code_task", "simple technical explanation")
    if GREETING.fullmatch(value):
        return _route("chat", "short greeting")
    return None


def _route(intent: str, reason: str, *, need_screen: bool = False,
           need_vision: bool = False, vision_scope: str = "active_window") -> dict[str, Any]:
    return {"intent": intent, "confidence": 1.0, "route_source": "fast_rule",
            "source": "fast_rule", "reason": reason, "need_screen": need_screen,
            "need_vision": need_vision, "permission_required": need_screen,
            "vision_scope": vision_scope}
