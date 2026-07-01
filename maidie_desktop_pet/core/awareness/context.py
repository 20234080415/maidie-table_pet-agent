from __future__ import annotations

from typing import Any


class AwarenessContext:
    def __init__(self, mouse_tracker: Any, window_tracker: Any,
                 app_tracker: Any | None = None, screen_reader: Any | None = None,
                 clipboard_tracker: Any | None = None) -> None:
        self.mouse_tracker, self.window_tracker = mouse_tracker, window_tracker
        self.app_tracker, self.screen_reader = app_tracker, screen_reader
        self.clipboard_tracker = clipboard_tracker

    def snapshot(self) -> dict[str, Any]:
        window = self.window_tracker.snapshot()
        result = {"mouse_state": self.mouse_tracker.state,
                  "window_state": window["window_state"],
                  "idle_time": round(self.mouse_tracker.idle_detector.idle_time, 1)}
        if self.app_tracker:
            result.update(self.app_tracker.snapshot())
        if self.screen_reader:
            result["screen"] = self.screen_reader.read()
        if self.clipboard_tracker:
            result["clipboard_changed"] = self.clipboard_tracker.changed()
        return result

    def screen_awareness_snapshot(self) -> dict[str, Any]:
        """Run the mandatory OCR + app + window pipeline for an explicit query."""
        screen = self.screen_reader.read(force=True) if self.screen_reader else {
            "screen_text": "", "context": "unknown", "status": "unavailable"
        }
        app = self.app_tracker.snapshot() if self.app_tracker else {
            "active_app": "unknown", "app_type": "unknown"
        }
        window = self.window_tracker.snapshot()
        candidates = (
            str(app.get("app_type", "unknown")),
            str(window.get("window_state", "unknown")),
            str(screen.get("context", "unknown")),
        )
        aliases = {"chat": "chatting", "browser": "browsing"}
        context = next((aliases.get(value, value) for value in candidates
                        if aliases.get(value, value) in {"coding", "browsing", "chatting"}), "unknown")
        return {
            "screen_text": str(screen.get("screen_text", "")),
            "app": str(app.get("active_app", "unknown")),
            "window": str(window.get("window_title", "")),
            "context": context,
            "tool_status": {
                "screen_ocr": str(screen.get("status", "ok")),
                "app_tracker": "ok",
                "window_tracker": "ok",
            },
        }
