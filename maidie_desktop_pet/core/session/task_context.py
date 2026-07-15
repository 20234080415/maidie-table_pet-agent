"""维护仅服务于当前对话的短期任务事实。

``LLMIntentRouter`` 用它从历史消息恢复事件时间，并解析“还有多久”等省略式追问；
这里不写入长期 Memory，避免临时事实跨 Session 泄漏或过期后继续生效。
"""

from __future__ import annotations

import re
from typing import Any


class ShortTermTaskContext:
    """保存显式事件时间，供紧邻的省略式追问复用。

    实例随 LLMIntentRouter 的会话状态创建或清空；``from_messages`` 可从 Session 历史
    重建上下文，但不会访问持久化 Memory。
    """

    TIME_TEXT = (r"(?:(?:上午|中午|下午|晚上|凌晨)\s*)?"
                 r"(?:\d{1,2}[.:]\d{1,2}|[零一二两三四五六七八九十\d]+点"
                 r"(?:[零一二两三四五六七八九十\d]+分?)?)")
    FACT = re.compile(
        rf"(?P<time>{TIME_TEXT})\s*(?:要)?(?P<event>[\u4e00-\u9fff]{{1,10}}?)"
        r"(?=，|,|。|！|？|\s*(?:现在|还有|还剩|$))"
    )
    FOLLOW_UP = re.compile(
        r"(?:还有|还剩)(?:多久|多长时间)?(?P<event>[\u4e00-\u9fff]{1,10})"
        r"(?:了|吗|呢)?[？?！!。.]?$"
    )

    def __init__(self) -> None:
        self.event_times: dict[str, str] = {}

    def observe(self, text: str) -> None:
        match = self.FACT.search(str(text))
        if match:
            self.event_times[match.group("event")] = match.group("time").replace(" ", "")

    def resolve(self, text: str) -> dict[str, Any] | None:
        match = self.FOLLOW_UP.search(str(text))
        if not match:
            return None
        event = match.group("event").rstrip("了吗呢")
        target = self.event_times.get(event)
        if not target:
            return None
        return {"intent": "task", "task_type": "time_delta", "needs_tools": True,
                "entities": {"target_time_text": target, "event": event}}

    @classmethod
    def from_messages(cls, messages: list[dict[str, Any]]) -> "ShortTermTaskContext":
        result = cls()
        for item in messages:
            if not isinstance(item, dict):
                continue
            text = item.get("content") or item.get("message") or item.get("text") or ""
            if item.get("role", "user") == "user":
                result.observe(str(text))
        return result
