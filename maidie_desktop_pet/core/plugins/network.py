from __future__ import annotations

import re
from typing import Any

from core.plugins.base import Plugin
from network.schemas import NetworkResult
from network.search import SearchService


class NetworkPlugin(Plugin):
    INTENT_PATTERN = re.compile(
        r"查一下|查查|搜索|搜一下|联网看看|联网查|最新|天气|现在几点|"
        r"官方文档|官网|新闻|实时|search|look up|weather|latest|official docs",
        re.IGNORECASE,
    )

    def __init__(self, settings: dict[str, Any] | None = None, search_service: Any | None = None) -> None:
        self._injected_service = search_service
        self.configure(settings or {})

    def configure(self, settings: dict[str, Any]) -> None:
        self.enabled = bool(settings.get("enabled", False))
        self.timeout = max(1, int(settings.get("timeout", 10)))
        self.show_sources = bool(settings.get("show_sources", True))
        self.search_provider = str(settings.get("search_provider", "tavily"))
        self.search_api_key = str(settings.get("search_api_key", ""))
        self.search_service = self._injected_service or SearchService(
            self.search_provider, self.search_api_key, self.timeout
        )

    def should_handle(self, message: str) -> bool:
        return self.enabled and bool(self.INTENT_PATTERN.search(message.strip()))

    def handle(self, message: str) -> dict:
        if not self.enabled:
            return NetworkResult(error="联网查询未开启。").to_dict()
        try:
            return self.search_service.search(message.strip())
        except Exception as exc:
            return NetworkResult(error=f"联网查询暂时不可用：{exc}").to_dict()
