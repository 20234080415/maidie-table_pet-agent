from __future__ import annotations

import ctypes
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable


class WindowTracker:
    """Reads and classifies the foreground window title without capturing content."""

    RULES = (
        ("coding", re.compile(r"visual studio|vscode|pycharm|intellij|android studio|terminal|powershell|cmd|github", re.I)),
        ("chat", re.compile(r"wechat|微信|qq|discord|slack|teams|telegram", re.I)),
        ("gaming", re.compile(r"steam|epic games|minecraft|valorant|league of legends|原神", re.I)),
        ("browser", re.compile(r"chrome|edge|firefox|opera|brave|safari|浏览器", re.I)),
    )
    SELF_WINDOW = re.compile(r"\bmaidie\b|maidie desktop pet|桌宠", re.I)

    def __init__(self, title_provider: Callable[[], str] | None = None,
                 info_provider: Callable[[], dict[str, Any]] | None = None,
                 self_pid: int | None = None) -> None:
        self._title_provider = title_provider or self._windows_title
        self._custom_title_provider = title_provider is not None
        self._info_provider = info_provider
        self._self_pid = os.getpid() if self_pid is None else self_pid
        self._last_external: dict[str, Any] | None = None

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

    def snapshot(self) -> dict[str, Any]:
        info = self._window_info()
        ignored = self._is_self_window(info)
        if ignored:
            external = self._find_external_window() if self._info_provider is None else None
            info = external or self._last_external or {}
        elif info.get("title"):
            self._last_external = dict(info)
        title = str(info.get("title", ""))
        result = {
            "window_state": self.state(title),
            "window_title": title,
            "process_name": str(info.get("process_name", "")),
            "window_class": str(info.get("window_class", "")),
            "ignored_self_window": ignored,
        }
        if ignored and not title:
            result.update({"window_state": "no_external_window",
                           "error": "no_external_window"})
        return result

    def _window_info(self) -> dict[str, Any]:
        try:
            if self._info_provider:
                return dict(self._info_provider() or {})
            if self._custom_title_provider:
                return {"title": self.title()}
            return self._windows_foreground_info()
        except Exception:
            return {"title": ""}

    def _is_self_window(self, info: dict[str, Any]) -> bool:
        pid = info.get("pid")
        if pid is not None:
            return int(pid) == self._self_pid
        return bool(self.SELF_WINDOW.search(
            f"{info.get('title', '')} {info.get('process_name', '')} {info.get('window_class', '')}"
        ))

    def _find_external_window(self) -> dict[str, Any] | None:
        if sys.platform != "win32":
            return None
        candidates: list[dict[str, Any]] = []
        user32 = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def visit(handle: int, _lparam: int) -> bool:
            if user32.IsWindowVisible(handle) and user32.GetWindowTextLengthW(handle) > 0:
                info = self._windows_handle_info(handle)
                if info.get("title") and not self._is_self_window(info):
                    candidates.append(info)
                    return False
            return True

        user32.EnumWindows(callback_type(visit), 0)
        return candidates[0] if candidates else None

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

    @classmethod
    def _windows_foreground_info(cls) -> dict[str, Any]:
        if sys.platform != "win32":
            return {"title": ""}
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        return cls._windows_handle_info(user32.GetForegroundWindow())

    @staticmethod
    def _windows_handle_info(handle: int) -> dict[str, Any]:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        length = user32.GetWindowTextLengthW(handle)
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, title_buffer, length + 1)
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(handle, class_buffer, len(class_buffer))
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        process_name = ""
        process = kernel32.OpenProcess(0x1000, False, pid.value)
        if process:
            try:
                size = ctypes.c_ulong(32768)
                path_buffer = ctypes.create_unicode_buffer(size.value)
                if kernel32.QueryFullProcessImageNameW(process, 0, path_buffer, ctypes.byref(size)):
                    process_name = Path(path_buffer.value).stem
            finally:
                kernel32.CloseHandle(process)
        return {"title": title_buffer.value, "pid": pid.value,
                "process_name": process_name, "window_class": class_buffer.value}
