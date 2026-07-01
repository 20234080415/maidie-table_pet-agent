from __future__ import annotations

from network.client import NetworkClient
from network.schemas import NetworkResult


class SearchService:
    """Search provider adapter. Version one supports Tavily."""

    def __init__(self, provider: str = "tavily", api_key: str = "", timeout: int = 10) -> None:
        self.provider = provider.strip().lower() or "tavily"
        self.api_key = api_key.strip()
        self.client = NetworkClient(timeout)

    def search(self, query: str) -> dict:
        if not self.api_key:
            return NetworkResult(error="尚未配置搜索 API Key。").to_dict()
        if self.provider != "tavily":
            return NetworkResult(error=f"暂不支持搜索服务：{self.provider}").to_dict()
        data, error = self.client.post_json(
            "https://api.tavily.com/search",
            {
                "api_key": self.api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": True,
            },
        )
        if error:
            return NetworkResult(error=error).to_dict()
        try:
            items = data.get("results", []) if isinstance(data, dict) else []
            sources = [
                {
                    "title": str(item.get("title", "网页")),
                    "url": str(item.get("url", "")),
                    "snippet": str(item.get("content", ""))[:600],
                }
                for item in items[:5]
                if isinstance(item, dict) and item.get("url")
            ]
            summary = str(data.get("answer", "")).strip() if isinstance(data, dict) else ""
            if not summary:
                summary = "\n".join(source["snippet"] for source in sources if source["snippet"])
            if not summary:
                return NetworkResult(error="没有找到可用的联网结果。").to_dict()
            return NetworkResult(
                ok=True,
                title=f"“{query}”的联网查询结果",
                summary=summary[:4000],
                sources=sources,
            ).to_dict()
        except (AttributeError, TypeError, ValueError) as exc:
            return NetworkResult(error=f"无法解析搜索结果：{exc}").to_dict()
