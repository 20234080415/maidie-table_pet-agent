from __future__ import annotations

from network.schemas import NetworkResult


class WebPageExtractor:
    """Reserved interface for a future opt-in webpage text extractor."""

    def extract(self, url: str) -> dict:
        return NetworkResult(
            type="webpage", error="网页正文提取功能尚未启用。"
        ).to_dict()
