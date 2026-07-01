from __future__ import annotations

import ctypes
import re
import sys
from typing import Callable


class WindowTracker:
    """Reads and classifies the foreground window title without capturing content."""

    RULES = (
        ("coding", re.compile(r"visual studio|vscode|pycharm|intellij|android studio|terminal|powershell|cmd|github", re.I)),
        ("chat", re.compile(r"wechat|微信|qq|discord|slack|teams|telegram", re.I)),
        ("gaming", re.compile(r"steam|epic games|minecraft|valorant|league of legends|原神", re.I)),
        ("browser", re.compile(r"chrome|edge|firefox|opera|brave|safari|浏览器", re.I)),
    )

    def __init__(self, title_provider: Callable[[], str] | None = None) -> None:
        self._title_provider = title_provider or self._windows_title

    def title(self) -> str:
        try:
            return str(self._title_provider() or "")
        except Exception:
            return ""

    def state(self, title: str | None = None) -> str:
        value = self.title() if title is None else title
        for state, pattern in self.RULES:
            if pattern.search(value):
                return state
        return "unknown"

    def snapshot(self) -> dict[str, str]:
        title = self.title()
        return {"window_state": self.state(title), "window_title": title}

    @staticmethod
    def _windows_title() -> str:
        if sys.platform != "win32":
            return ""
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        handle = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(handle)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, buffer, length + 1)
        return buffer.value
