from __future__ import annotations

import re
from typing import Any

from core.tools.base import Tool, ToolResult


class SearchTool(Tool):
    name = "search"
    PATTERN = re.compile(r"查资料|查一下|查询|搜索|最新|新闻|search|look up|latest", re.I)

    def __init__(self, network_plugin: Any) -> None:
        self.network_plugin = network_plugin

    def match(self, query: str) -> bool:
        return bool(self.PATTERN.search(query.strip()))

    def run(self, query: str) -> ToolResult:
        return {"type": self.name, "raw": self.network_plugin.handle(query), "source": "api"}
