from __future__ import annotations

import logging
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

    def run(self, query: str, raw_user_text: str = "",
            query_source: str = "explicit_user_text") -> ToolResult:
        query = str(query).strip()
        if not query:
            raw = {"ok": False, "error": "搜索内容为空。",
                   "failure_reason": "EMPTY_QUERY", "result_count": 0}
        else:
            try:
                raw = self.network_plugin.handle(query)
                if not isinstance(raw, dict):
                    raw = {"ok": False, "error": "invalid search response",
                           "failure_reason": "UNKNOWN_ERROR"}
            except TimeoutError as exc:
                raw = {"ok": False, "error": str(exc), "failure_reason": "TIMEOUT"}
            except OSError as exc:
                raw = {"ok": False, "error": str(exc), "failure_reason": "NETWORK_ERROR"}
            except Exception as exc:
                raw = {"ok": False, "error": str(exc), "failure_reason": "UNKNOWN_ERROR"}
        raw = dict(raw)
        raw["show_sources"] = bool(getattr(self.network_plugin, "show_sources", True))
        count = int(raw.get("result_count", len(raw.get("sources", []) or [])))
        raw["query"] = query
        reason = str(raw.get("failure_reason", ""))
        if raw.get("error") and not reason:
            reason = "UNKNOWN_ERROR"
            raw["failure_reason"] = reason
        raw["result_count"] = count
        logging.getLogger(__name__).info(
            "search_debug raw_user_text=%r resolved_search_query=%r "
            "query_source=%s selected_tool=search tavily_result_count=%d failure_reason=%s",
            raw_user_text or query, query, query_source or "missing", count, reason or "NONE",
        )
        return {"type": self.name, "raw": raw, "source": "api"}
