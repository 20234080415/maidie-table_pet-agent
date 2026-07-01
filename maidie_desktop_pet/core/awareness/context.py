from __future__ import annotations

from typing import Any


class AwarenessContext:
    def __init__(self, mouse_tracker: Any, window_tracker: Any) -> None:
        self.mouse_tracker, self.window_tracker = mouse_tracker, window_tracker

    def snapshot(self) -> dict[str, Any]:
        window = self.window_tracker.snapshot()
        return {"mouse_state": self.mouse_tracker.state,
                "window_state": window["window_state"],
                "idle_time": round(self.mouse_tracker.idle_detector.idle_time, 1)}
