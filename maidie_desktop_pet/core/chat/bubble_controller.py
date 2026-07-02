from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QObject


class BubbleController(QObject):
    """Owns the streaming bubble lifecycle without rebuilding its text."""

    def __init__(self, bubble: Any, reposition: Callable[[], None], parent=None) -> None:
        super().__init__(parent)
        self._bubble = bubble
        self._reposition = reposition
        if hasattr(bubble, "layout_changed"):
            bubble.layout_changed.connect(reposition)

    def begin_stream(self, metadata: dict[str, Any] | None = None) -> None:
        self._bubble.begin_stream()
        if metadata and metadata.get("source") == "codex":
            self._bubble.append_text("⌘ ")
        self._reposition()

    def append_text(self, fragment: str) -> None:
        self._bubble.append_text(fragment)
        self._bubble.raise_()

    def complete_stream(self, response: dict[str, Any]) -> None:
        # The visible text has already arrived incrementally. Completion only
        # controls lifetime; it must never replace the accumulated document.
        duration = min(9000, max(2800, len(str(response.get("text", ""))) * 90))
        self._bubble.finish_stream(duration)
        self._reposition()
