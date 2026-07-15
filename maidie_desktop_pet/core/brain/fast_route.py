"""为低风险、可确定识别的请求提供 Brain 快速路由。

规则在 LLM Router 之前处理时间、天气、Vision scope 等明确意图以降低延迟；模糊输入
返回空结果并交还 ``LLMIntentRouter``，避免正则越权替代语义判断。
"""

from __future__ import annotations

import re
from typing import Any

from core.vision.intent_rules import (VisionScope, detect_vision_scope,
                                      is_cursor_region_request, is_explicit_scope_request)


TIME = re.compile(r"现在几点|现在的时间|今天几号|今天星期几|当前时间|现在时间|\b(?:time|date)\b", re.I)
TIME_DELTA = re.compile(r"(?:还有|还剩|距离|到).*(?:多久|多长时间)|(?:多久|多长时间).*(?:下课|开会|考试|出门)", re.I)
TARGET_TIME = re.compile(
    r"(?P<time>(?:(?:上午|中午|下午|晚上|凌晨)\s*)?(?:[零一二两三四五六七八九十\d]+点(?:[零一二两三四五六七八九十\d]+分?)?|\d{1,2}[.:]\d{1,2}))"
)
WEATHER = re.compile(r"天气|下雨|带伞|气温|温度|多少度|冷不冷|weather|temperature", re.I)
SCREEN = re.compile(
    r"看屏幕|看一下屏幕|看看我屏幕|看看我的屏幕|你看看我现在|当前窗口|屏幕上|截图|"
    r"看图|图片里|这张图|这个报错|帮我看一下这个报错|帮我看一下屏幕|"
    r"你看看我现在屏幕这个题怎么写|你看看我现在屏幕这个报错|"
    r"你能.*(?:看到|看见).*(?:屏幕|桌面)", re.I,
)
AMBIGUOUS_VISION = re.compile(
    r"^(?:这个怎么弄|这是啥情况|帮我看看|帮我看一下|看一下|这个什么意思|这个题怎么写|这题怎么做|怎么办)"
    r"[？?！!。.\s]*$", re.I,
)
TECHNICAL = re.compile(r"代码|编译|linux|cmake|cmakelists\.txt|makefile|python|api|报错|函数|重构", re.I)
EXPLANATION = re.compile(r"是什么意思|怎么用|有什么作用|解释", re.I)
GREETING = re.compile(r"^(?:你好|嗨|hello|hi|嗯|好的)[！!。.？?\s]*$", re.I)
SEARCH = re.compile(r"搜索|搜|继续查|帮我查|查一下|查询|search|look up", re.I)
COMPLEX_WEATHER = re.compile(r"适合|穿什么|安排|出去玩|建议|推荐|应该", re.I)
PROJECT_CODING_REQUEST = re.compile(
    r"分析(?:一下|下|看看)?(?:我(?:的)?|当前|这个)?(?:这个)?项目|"
    r"(?:帮我)?(?:修|修复|重构|检查|看看).*(?:项目|代码库|仓库)|"
    r"(?:生成|给我).*(?:patch|补丁)|测试怎么写|功能应该加在哪里|"
    r"\b(?:analy[sz]e (?:my |the )?(?:project|repo)|fix (?:this )?bug|"
    r"refactor (?:this )?module|generate (?:a )?patch|test plan)\b",
    re.I,
)


def is_simple_time_query(text: str) -> bool:
    """判断请求是否可由本地 TimeTool 直接、完整回答。"""
    return bool(TIME.search(str(text).strip()))


def is_weather_query(text: str) -> bool:
    """判断文本是否包含天气事实需求，不区分是否还需要建议。"""
    return bool(WEATHER.search(str(text).strip()))


def is_simple_weather_query(text: str) -> bool:
    """区分纯天气事实与需要 LLM 综合判断的复杂天气问题。"""
    value = str(text).strip()
    return is_weather_query(value) and not bool(COMPLEX_WEATHER.search(value))


def is_coding_agent_request(text: str) -> bool:
    """识别明确要求操作项目上下文的 Coding Agent 请求。"""
    value = str(text).strip()
    compact = re.sub(r"[\s'’\"`_-]+", "", value).lower()
    explicitly_calls_cli = (
        ("opencode" in compact or "codex" in compact)
        and bool(re.search(r"调用|使用|用一下|让|请|帮我|分析|检查|修复|看看|run|use|ask", value, re.I))
    )
    return explicitly_calls_cli or bool(PROJECT_CODING_REQUEST.search(value))


def fast_route(text: str) -> dict[str, Any] | None:
    """返回高置信度的标准化 route；无法确定时返回 ``None``。"""
    value = str(text).strip()
    scope = detect_vision_scope(value)
    if scope in {VisionScope.SELECTED_REGION, VisionScope.FULLSCREEN} and is_explicit_scope_request(value):
        return _route("vision", f"explicit {scope.value} request", need_screen=True,
                      need_vision=True, vision_scope=scope.value)
    if is_cursor_region_request(value):
        return _route("vision", "explicit cursor-region request", need_screen=True,
                      need_vision=True, vision_scope="cursor_region")
    if AMBIGUOUS_VISION.fullmatch(value):
        return _route("clarification", "ambiguous visual reference", need_screen=False,
                      need_vision=False)
    if is_coding_agent_request(value):
        return _route("code_task", "explicit local coding agent request",
                      task_type="code_task", needs_tools=True)
    if TECHNICAL.search(value) and not re.search(r"屏幕|当前窗口|打开的软件", value) and (
            EXPLANATION.search(value) or re.search(r"怎么修|为什么不执行|怎么重构|帮我看看", value)):
        return _route("code_task", "technical task", task_type="code_task")
    if re.search(r"你能.*(?:看到|看见).*(?:打开的)?软件", value):
        return _route("vision", "explicit screen request", task_type="screen_understanding",
                      needs_tools=True, need_screen=True, need_vision=True)
    if SCREEN.search(value):
        return _route("vision", "explicit screen request", task_type="screen_understanding",
                      needs_tools=True, need_screen=True, need_vision=True)
    if TIME_DELTA.search(value):
        target = TARGET_TIME.search(value)
        if target:
            tail = value[target.end():]
            event_match = (None if re.match(r"\s*(?:现在|还有|还剩)", tail) else
                           re.match(r"\s*(?:要)?([\u4e00-\u9fff]{1,10}?)(?=，|,|。|！|？|\s*(?:现在|还有|还剩|$))", tail))
            event = event_match.group(1) if event_match else ""
            return _route("task", "deterministic time delta", task_type="time_delta",
                          needs_tools=True, entities={"target_time_text": target.group("time").replace(" ", ""),
                                                      "event": event})
    if is_simple_time_query(value):
        return _route("task", "deterministic time query", task_type="time_now", needs_tools=True)
    if is_weather_query(value):
        locations = re.findall(r"([\u4e00-\u9fff]{2,8})(?=天气|会下雨)", value)
        location = locations[-1].replace("今天", "").replace("明天", "") if locations else ""
        return _route("task", "deterministic weather query", task_type="weather",
                      needs_tools=True, entities={"location": location})
    if SEARCH.search(value):
        query = re.sub(r"^(?:帮我)?(?:搜一下|搜索一下|查一下|查询一下?)\s*", "", value).strip()
        return _route("task", "deterministic search request", task_type="search",
                      needs_tools=True, entities={"query": query})
    if GREETING.fullmatch(value):
        return _route("chat", "short greeting")
    return None


def _route(intent: str, reason: str, *, task_type: str = "none", needs_tools: bool = False,
           entities: dict[str, Any] | None = None, need_screen: bool = False,
           need_vision: bool = False, vision_scope: str = "") -> dict[str, Any]:
    return {"intent": intent, "confidence": 1.0, "route_source": "fast_rule",
            "source": "fast_rule", "reason": reason, "need_screen": need_screen,
            "need_vision": need_vision, "permission_required": need_screen,
            "vision_scope": vision_scope, "task_type": task_type,
            "needs_tools": needs_tools, "entities": dict(entities or {})}
