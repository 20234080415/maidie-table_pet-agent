from __future__ import annotations

import re
from datetime import datetime

from core.tools.base import Tool, ToolResult


class TimeTool(Tool):
    name = "time"
    PATTERN = re.compile(r"时间|现在几点|几点|日期|星期|\b(time|today|now|date)\b", re.I)

    def match(self, query: str) -> bool:
        return bool(self.PATTERN.search(query.strip()))

    def run(self, query: str) -> ToolResult:
        now = datetime.now().astimezone()
        return {"type": "time", "raw": {
            "iso": now.isoformat(), "timezone": str(now.tzinfo), "weekday": now.weekday()
        }, "source": "local"}
