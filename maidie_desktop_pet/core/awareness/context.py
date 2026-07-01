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
