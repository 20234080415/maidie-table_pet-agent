from __future__ import annotations

import re
from typing import Any


class ShortTermTaskContext:
    """Keeps explicit event times for immediate conversational follow-ups."""

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
