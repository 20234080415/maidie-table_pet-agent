from __future__ import annotations

import ctypes
import sys


class ClipboardTracker:
    """Detects clipboard changes without reading clipboard contents."""

    def __init__(self) -> None:
        self._last_sequence = self._sequence()

    def changed(self) -> bool:
        current = self._sequence()
        changed = bool(current and self._last_sequence and current != self._last_sequence)
        self._last_sequence = current
        return changed

    @staticmethod
    def _sequence() -> int:
        if sys.platform != "win32":
            return 0
        return int(ctypes.windll.user32.GetClipboardSequenceNumber())
