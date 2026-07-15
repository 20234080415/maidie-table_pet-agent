"""跟踪剪贴板文本是否发生变化及其新鲜度。

该 Tracker 只由上层显式喂入内容，不自行静默读取系统剪贴板；Planner 可借助变化时间
判断是否需要确认把最近文本用于 Search。
"""

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
