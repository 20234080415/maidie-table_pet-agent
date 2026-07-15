"""把网络 SearchService 封装为可配置的 Network Plugin。

``SearchTool`` 通过本模块执行检索并取得统一 schema；Plugin 负责 API 配置、查询清洗和
异常归一化，不决定何时联网，也不生成最终回答。
"""

from __future__ import annotations

import re
from typing import Any

from core.plugins.base import Plugin
from network.schemas import NetworkResult
from network.search import SearchService


class NetworkPlugin(Plugin):
    """管理 SearchService 配置并返回结构化网络检索结果。

    实例随 ToolRegistry 相关依赖常驻，设置更新时可重新 configure；每次 handle 独立执行，
    不保存对话上下文。
    """
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
            return NetworkResult(error="联网查询未开启。",
                                 failure_reason=("API_KEY_MISSING" if not self.search_api_key
                                                 else "UNKNOWN_ERROR")).to_dict()
        try:
            return self.search_service.search(message.strip())
        except Exception as exc:
            return NetworkResult(error=f"联网查询暂时不可用：{exc}",
                                 failure_reason="UNKNOWN_ERROR").to_dict()
