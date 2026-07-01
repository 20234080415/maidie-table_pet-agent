from __future__ import annotations

import re
from datetime import datetime

from core.tools.base import Tool, ToolResult


class TimeTool(Tool):
    name = "time"
    PATTERN = re.compile(r"时间|现在几点|日期|星期|\b(today|now)\b", re.IGNORECASE)

    def match(self, query: str) -> bool:
        return bool(self.PATTERN.search(query.strip()))

    def run(self, query: str) -> ToolResult:
        now = datetime.now().astimezone()
        weekdays = "一二三四五六日"
        return {
            "type": "time",
            "text": f"现在时间是：{now:%Y-%m-%d %H:%M:%S}，星期{weekdays[now.weekday()]}。",
            "raw": {"iso": now.isoformat(), "timezone": str(now.tzinfo)},
            "source": "local",
        }
