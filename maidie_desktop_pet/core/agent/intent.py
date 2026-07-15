"""保留旧 Agent 调用方使用的粗粒度意图模型。

生产意图路由已迁移到 ``core.brain.LLMIntentRouter``；本模块只维持兼容接口和测试，
新 Router/Planner 逻辑不应继续添加到这里。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any


class Intent(str, Enum):
    """旧 AgentCore 可识别的有限意图集合。"""
    SCREEN_AWARENESS = "SCREEN_AWARENESS"
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
    SYSTEM_PATTERN = re.compile(r"读取文件|查看文件|搜索文件|查找文件|创建文件|新建文件|打开应用|打开文件夹|切换窗口|截图|剪贴板|notepad|vscode|chrome", re.I)

    def __init__(self, tool_registry: Any | None = None) -> None:
        self.tool_registry = tool_registry

    def detect(self, message: str) -> str:
        text = message.strip()
        # Reality questions always win over technical/chat classification.
        if self.is_screen_related(text):
            return Intent.SCREEN_AWARENESS.value
        # Decision must win over a weather/time match (e.g. “明天适合跑步吗”).
        if self.DECISION_PATTERN.search(text) or self.MULTI_CONDITION_PATTERN.search(text) or self.SYSTEM_PATTERN.search(text):
            return Intent.DECISION_TASK.value
        if self.FACT_PATTERN.search(text):
            return Intent.DIRECT_TOOL.value
        if self.tool_registry and self.tool_registry.match(text):
            return Intent.DIRECT_TOOL.value
        return Intent.CHAT.value

    @classmethod
    def is_screen_related(cls, message: str) -> bool:
        return bool(cls.SCREEN_PATTERN.search(message.strip()))

    def requires_planner(self, message: str) -> bool:
        return self.detect(message) == Intent.DECISION_TASK.value
    SCREEN_PATTERN = re.compile(
        r"你能.*(?:看到|看见).*(?:屏幕|桌面)|(?:看到|看见)我在做什么|"
        r"你知道我在干嘛|我现在在(?:干嘛|做什么)|你能监控我吗|"
        r"你知道我在写代码吗|(?:屏幕|桌面).*(?:有什么|是什么|内容)|"
        r"\b(?:can you see my screen|what am i doing|monitor my screen)\b",
        re.IGNORECASE,
    )
