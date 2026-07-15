"""提供无需 LLM 的本地时间事实与事件倒计时计算。

Planner 可选择当前时间或 ``delta_until`` action；Tool 使用注入时钟便于测试，并返回
结构化时间数据，由 Synthesizer 负责最终表达。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable

from core.tools.base import Tool, ToolResult


class TimeTool(Tool):
    """以本地时区时钟回答时间查询和目标时间差。

    实例通常无状态并随 Registry 常驻；``now_provider`` 注入使边界时间和时区行为可测试。
    """
    name = "time"
    PATTERN = re.compile(r"时间|现在几点|几点|日期|星期|\b(time|today|now|date)\b", re.I)

    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self._now_provider = now_provider or (lambda: datetime.now().astimezone())

    def match(self, query: str) -> bool:
        return bool(self.PATTERN.search(query.strip()))

    def run(self, query: str) -> ToolResult:
        now = self._now_provider()
        return {"type": "time", "raw": {
            "iso": now.isoformat(), "timezone": str(now.tzinfo), "weekday": now.weekday()
        }, "source": "local"}

    def execute(self, action: str = "now", *, target_time_text: str = "",
                event: str = "") -> ToolResult:
        """执行当前时间或倒计时 action，并返回标准化时间事实。"""
        if action != "delta_until":
            return self.run("now")
        now = self._now_provider()
        target = self._parse_target(target_time_text, now)
        if target is None:
            return {"type": "time_delta", "raw": {"error": "无法识别目标时间",
                                                       "target_time_text": target_time_text},
                    "source": "local"}
        minutes = int((target - now).total_seconds() // 60)
        if minutes < 0:
            raw = {"status": "elapsed", "now": now.strftime("%H:%M"),
                   "target": target.strftime("%H:%M"), "event": event,
                   "remaining_minutes": 0, "remaining_text": "已过"}
        else:
            hours, remainder = divmod(minutes, 60)
            remaining = ((f"{hours}小时" if hours else "") +
                         (f"{remainder}分钟" if remainder or not hours else ""))
            raw = {"status": "upcoming", "now": now.strftime("%H:%M"),
                   "target": target.strftime("%H:%M"), "event": event,
                   "remaining_minutes": minutes, "remaining_text": remaining}
        return {"type": "time_delta", "raw": raw, "source": "local"}

    @classmethod
    def _parse_target(cls, text: str, now: datetime) -> datetime | None:
        value = str(text).strip().replace("。", ".").replace("：", ":")
        match = re.fullmatch(r"(\d{1,2})[.:](\d{1,2})", value)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            if hour <= 7 and now.hour >= 12:
                hour += 12
        else:
            match = re.fullmatch(r"(?:(上午|中午|下午|晚上|凌晨))?([零一二两三四五六七八九十\d]{1,3})点"
                                 r"(?:([零一二两三四五六七八九十\d]{1,3})分?)?", value)
            if not match:
                return None
            period, hour_text, minute_text = match.groups()
            hour = cls._number(hour_text)
            minute = cls._number(minute_text) if minute_text else 0
            if period in {"下午", "晚上"} and hour < 12:
                hour += 12
            elif period == "中午" and hour < 11:
                hour += 12
            elif period == "凌晨" and hour == 12:
                hour = 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    @staticmethod
    def _number(text: str | None) -> int:
        if not text:
            return 0
        if text.isdigit():
            return int(text)
        digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                  "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        if text == "十":
            return 10
        if "十" in text:
            left, right = text.split("十", 1)
            return (digits.get(left, 1) * 10) + digits.get(right, 0)
        return digits.get(text, -1)
