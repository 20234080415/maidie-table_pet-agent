"""把网络检索 Plugin 适配为 Brain 可调用的 Search Tool。

Planner 提供查询及来源，Tool 调用 ``NetworkPlugin`` 并统一网络/超时/空结果元数据；
引用展示与最终措辞由 Synthesizer 决定。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.tools.base import Tool, ToolResult


class SearchTool(Tool):
    """执行显式或已确认来源的网络查询。

    实例复用注入的 NetworkPlugin；每次调用保留 query source 和失败原因，使上层能
    区分无查询、网络故障与低质量结果。
    """
    name = "search"
    PATTERN = re.compile(r"查资料|查一下|查询|搜索|最新|新闻|search|look up|latest", re.I)

    def __init__(self, network_plugin: Any) -> None:
        self.network_plugin = network_plugin

    def match(self, query: str) -> bool:
        return bool(self.PATTERN.search(query.strip()))

    def run(self, query: str, raw_user_text: str = "",
            query_source: str = "explicit_user_text") -> ToolResult:
        """检索 ``query`` 并返回带来源、计数和失败分类的 ToolResult。"""
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
