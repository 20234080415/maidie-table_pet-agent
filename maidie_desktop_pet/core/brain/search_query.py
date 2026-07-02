from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolvedSearchQuery:
    query: str
    source: str


class SearchQueryResolver:
    """Resolve explicit and contextual search requests without involving the LLM."""

    SEARCH_INTENT = re.compile(r"搜索|搜(?:一下)?|查(?:一下|查)?|查询|search|look up", re.I)
    CLIPBOARD = re.compile(r"(?:搜|搜索|查).*(?:剪贴板|刚复制)", re.I)
    ELLIPSIS = re.compile(
        r"^(?:现在可以搜索吗|帮我搜一下|帮我查一下|搜刚才那个|再搜一次|重新搜|继续搜)[？?！!。.\s]*$",
        re.I,
    )
    EXPLICIT = re.compile(
        r"^(?:请|麻烦|去|现在)?(?:给我)?(?:帮我)?(?:搜索一下|搜一下|搜索|搜|查一下|查查|查询|查)\s*(?P<query>.+?)\s*[？?！!。]*$",
        re.I,
    )

    def resolve(self, raw_user_text: str, memory: Any = None,
                clipboard_text: str = "") -> ResolvedSearchQuery:
        text = str(raw_user_text).strip()
        if self.CLIPBOARD.search(text):
            value = str(clipboard_text).strip()
            if value:
                self._remember(memory, value)
                return ResolvedSearchQuery(value, "clipboard")
            return ResolvedSearchQuery("", "missing")
        match = self.EXPLICIT.match(text)
        if match and not self.ELLIPSIS.match(text):
            query = match.group("query").strip()
            if query:
                self._remember(memory, query)
                return ResolvedSearchQuery(query, "explicit_user_text")
        if self.ELLIPSIS.match(text):
            query = self._last_query(memory)
            if query:
                return ResolvedSearchQuery(query, "last_search_query")
            value = str(clipboard_text).strip()
            if value:
                self._remember(memory, value)
                return ResolvedSearchQuery(value, "clipboard")
            return ResolvedSearchQuery("", "missing")
        if self.SEARCH_INTENT.search(text):
            self._remember(memory, text)
            return ResolvedSearchQuery(text, "explicit_user_text")
        return ResolvedSearchQuery("", "missing")

    @staticmethod
    def _last_query(memory: Any) -> str:
        try:
            return str(memory.get_last_search_query()).strip()
        except (AttributeError, TypeError):
            return str(getattr(memory, "last_search_query", "")).strip()

    @staticmethod
    def _remember(memory: Any, query: str) -> None:
        if memory is None:
            return
        try:
            memory.set_last_search_query(query)
        except AttributeError:
            setattr(memory, "last_search_query", query)
