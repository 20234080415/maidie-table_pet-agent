from __future__ import annotations

from typing import Any

from core.tools.base import Tool, ToolResult


class ScreenTool(Tool):
    name = "screen"

    def __init__(self, awareness_provider: Any) -> None:
        self.awareness_provider = awareness_provider

    def match(self, query: str) -> bool:
        return False  # Only BrainRouter may invoke screen capture.

    def run(self, query: str) -> ToolResult:
        return {"type": self.name,
                "raw": self.awareness_provider.screen_awareness_snapshot(),
                "source": "local"}
