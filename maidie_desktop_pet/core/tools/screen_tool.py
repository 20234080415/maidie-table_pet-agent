from __future__ import annotations

from typing import Any

from core.tools.base import Tool, ToolResult
from core.vision.errors import VisionAPIError, VisionCaptureError, VisionConfigError


class ScreenTool(Tool):
    name = "screen"

    def __init__(self, awareness_provider: Any = None, vision_service: Any = None) -> None:
        self.awareness_provider = awareness_provider
        self.vision_service = vision_service

    def match(self, query: str) -> bool:
        return False  # Only BrainRouter may invoke screen capture.

    def run(self, query: str) -> ToolResult:
        try:
            if self.vision_service is not None:
                context = self.vision_service.capture_and_analyze(query)
                raw = {"vision_context": context.to_dict(), "task_type": context.task_type,
                       "confidence": context.confidence}
            else:
                raw = self.awareness_provider.screen_awareness_snapshot()
            if not isinstance(raw, dict):
                raise TypeError("screen awareness returned invalid data")
            return {"type": self.name, "raw": dict(raw),
                    "source": "qwen_vl" if self.vision_service is not None else "local"}
        except VisionConfigError as exc:
            return self._vision_error("vision_config_missing", str(exc))
        except VisionCaptureError as exc:
            return self._vision_error("vision_capture_failed", str(exc))
        except VisionAPIError as exc:
            return self._vision_error("vision_api_failed", str(exc))
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

    def _vision_error(self, code: str, message: str) -> ToolResult:
        return {"type": self.name, "raw": {"error": message, "error_code": code},
                "source": "qwen_vl"}
