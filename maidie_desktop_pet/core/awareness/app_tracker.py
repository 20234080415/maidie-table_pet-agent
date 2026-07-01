from __future__ import annotations

import ctypes
import re
import sys
from pathlib import Path
from time import monotonic
from typing import Callable

from core.awareness.window_tracker import WindowTracker


class AppTracker:
    """Identifies the foreground executable and semantic app category."""

    RULES = (
        ("coding", re.compile(r"code|vscode|pycharm|devenv|idea|sublime|notepad\+\+", re.I)),
        ("browsing", re.compile(r"chrome|msedge|firefox|brave|opera", re.I)),
        ("chatting", re.compile(r"wechat|qq|discord|slack|teams|telegram", re.I)),
        ("gaming", re.compile(r"steam|epic|minecraft|valorant|league|genshin", re.I)),
    )

    def __init__(self, info_provider: Callable[[], tuple[str, str]] | None = None,
                 clock: Callable[[], float] = monotonic, switch_window: float = 300.0) -> None:
        self._provider = info_provider or self._foreground_info
        self._clock, self.switch_window = clock, switch_window
        self._last_app = ""
        self._switches: list[float] = []

    def snapshot(self) -> dict[str, object]:
        try:
            app, title = self._provider()
        except Exception:
            app, title = "", ""
        now = self._clock()
        if self._last_app and app and app.lower() != self._last_app.lower():
            self._switches.append(now)
        if app:
            self._last_app = app
        self._switches = [value for value in self._switches if now - value <= self.switch_window]
        combined = f"{app} {title}"
        app_type = next((kind for kind, pattern in self.RULES if pattern.search(combined)), "unknown")
        return {"active_app": app or "unknown", "app_type": app_type,
                "window_title": title, "switch_count": len(self._switches)}

    @staticmethod
    def _foreground_info() -> tuple[str, str]:
        title = WindowTracker().title()
        if sys.platform != "win32":
            return "", title
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                                       ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        process = kernel32.OpenProcess(0x1000, False, pid.value)
        if not process:
            return "", title
        try:
            size = ctypes.c_ulong(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                return Path(buffer.value).stem, title
            return "", title
        finally:
            kernel32.CloseHandle(process)
