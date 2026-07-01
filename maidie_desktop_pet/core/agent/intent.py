from __future__ import annotations

import re
from enum import Enum
from typing import Any


class Intent(str, Enum):
    DIRECT_TOOL = "DIRECT_TOOL"
    DECISION_TASK = "DECISION_TASK"
    CHAT = "CHAT"


class IntentDetector:
    """Deterministic, high-priority intent gate for Agent Router V2."""

    DECISION_PATTERN = re.compile(
        r"适不适合|是否适合|适合.*吗|能不能|是否应该|建议|去不去|要不要|该不该|"
        r"值不值得|推荐|\b(should|recommend|advice|suitable|can i)\b",
        re.IGNORECASE,
    )
    FACT_PATTERN = re.compile(
        r"天气|气温|温度|下雨|几点|时间|日期|星期|搜索|查询|查一下|最新|"
        r"\b(weather|temperature|time|date|search|look up|latest)\b",
        re.IGNORECASE,
    )
    MULTI_CONDITION_PATTERN = re.compile(r"并且|而且|同时|然后|以及|；|;|.+(?:天气|时间).+(?:建议|推荐)")

    def __init__(self, tool_registry: Any | None = None) -> None:
        self.tool_registry = tool_registry

    def detect(self, message: str) -> str:
        text = message.strip()
        # Decision must win over a weather/time match (e.g. “明天适合跑步吗”).
        if self.DECISION_PATTERN.search(text) or self.MULTI_CONDITION_PATTERN.search(text):
            return Intent.DECISION_TASK.value
        if self.FACT_PATTERN.search(text):
            return Intent.DIRECT_TOOL.value
        if self.tool_registry and self.tool_registry.match(text):
            return Intent.DIRECT_TOOL.value
        return Intent.CHAT.value

    def requires_planner(self, message: str) -> bool:
        return self.detect(message) == Intent.DECISION_TASK.value
