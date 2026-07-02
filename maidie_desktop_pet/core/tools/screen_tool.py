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
        try:
            raw = self.awareness_provider.screen_awareness_snapshot()
            if not isinstance(raw, dict):
                raise TypeError("screen awareness returned invalid data")
            return {"type": self.name, "raw": dict(raw), "source": "local"}
        except Exception as exc:
            return {"type": self.name,
                    "raw": {"error": str(exc), "error_code": "screen_tool_failed",
                            "screen_debug": {"intent": "screen",
                                             "active_window": "",
                                             "ignored_self_window": False,
                                             "screenshot_source": "failed",
                                             "ocr_enabled": False,
                                             "ocr_text_length": 0}},
                    "source": "local"}
