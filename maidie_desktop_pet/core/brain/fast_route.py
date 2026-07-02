from __future__ import annotations

import re
from typing import Any


TIME = re.compile(r"现在几点|今天几号|今天星期几|当前时间|现在时间|\b(?:time|date)\b", re.I)
WEATHER = re.compile(r"天气怎么样|今天天气|今天下雨吗|今天冷不冷|现在多少度|(?:长沙|深圳)天气", re.I)
SCREEN = re.compile(
    r"看看我的屏幕|看屏幕|当前窗口|屏幕上是什么|这个报错|这题怎么写|"
    r"你能.*(?:看到|看见).*(?:屏幕|桌面)", re.I,
)
TECHNICAL = re.compile(r"代码|编译|linux|cmake|makefile|python|api|报错", re.I)
EXPLANATION = re.compile(r"是什么意思|怎么用|有什么作用", re.I)
GREETING = re.compile(r"^(?:你好|嗨|hello|hi|嗯|好的)[！!。.？?\s]*$", re.I)
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
    if SCREEN.search(value):
        return _route("screen", "explicit screen request")
    if is_simple_time_query(value):
        return _route("task", "deterministic time query")
    if is_weather_query(value):
        return _route("task", "deterministic weather query")
    if TECHNICAL.search(value) and EXPLANATION.search(value):
        return _route("code_task", "simple technical explanation")
    if GREETING.fullmatch(value):
        return _route("chat", "short greeting")
    return None


def _route(intent: str, reason: str) -> dict[str, Any]:
    return {"intent": intent, "confidence": 1.0, "route_source": "fast_rule",
            "source": "fast_rule", "reason": reason}
