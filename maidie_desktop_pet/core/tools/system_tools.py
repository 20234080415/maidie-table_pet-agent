from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from core.tools.base import Tool, ToolResult


class SystemTool(Tool):
    """Explicit OS operations with deny-by-default mutation controls."""

    name = "system"
    DANGEROUS_ACTIONS = {"delete_file", "execute_script", "system_command"}
    CONFIRMATION_ACTIONS = {"create_file", "open_app", "open_folder", "switch_window", "copy_clipboard"}
    READ_ONLY_ACTIONS = {"read_file", "search_files", "screenshot"}
    APPS = {"notepad": ["notepad.exe"], "vscode": ["code"],
            "chrome": ["cmd", "/c", "start", "", "chrome"]}
    PATTERN = re.compile(r"读取文件|搜索文件|查找文件|创建文件|打开应用|打开文件夹|切换窗口|截图|剪贴板|notepad|vscode|chrome", re.I)

    def __init__(self, confirmation_callback: Callable[[str, dict[str, Any]], bool] | None = None,
                 clipboard_writer: Callable[[str], None] | None = None) -> None:
        self.confirmation_callback = confirmation_callback
        self.clipboard_writer = clipboard_writer or self._write_clipboard

    def match(self, query: str) -> bool:
        return bool(self.PATTERN.search(query))

    def run(self, query: str) -> ToolResult:
        return {"type": "system", "raw": {"error": "system actions require a structured action"}, "source": "local"}

    def execute(self, action: str, params: dict[str, Any] | None = None,
                confirmed: bool = False) -> ToolResult:
        params = dict(params or {})
        if action in self.DANGEROUS_ACTIONS:
            return self._denied(action, "dangerous action is not implemented")
        if action not in self.READ_ONLY_ACTIONS | self.CONFIRMATION_ACTIONS:
            return self._denied(action, "unsupported action")
        if action in self.CONFIRMATION_ACTIONS and not confirmed:
            if not self.confirmation_callback or not self.confirmation_callback(action, params):
                return self._denied(action, "user confirmation required")
        try:
            raw = getattr(self, f"_{action}")(params)
            return {"type": "system", "raw": {"action": action, **raw}, "source": "local"}
        except Exception as exc:
            return {"type": "system", "raw": {"action": action, "error": str(exc)}, "source": "local"}

    @staticmethod
    def _denied(action: str, reason: str) -> ToolResult:
        return {"type": "system", "raw": {"action": action, "error": reason, "denied": True}, "source": "local"}

    @staticmethod
    def _read_file(params: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(params["path"])).expanduser().resolve()
        size = path.stat().st_size
        if size > 2_000_000:
            raise ValueError("file exceeds 2 MB read limit")
        return {"path": str(path), "content": path.read_text(encoding=str(params.get("encoding", "utf-8")), errors="replace"), "size": size}

    @staticmethod
    def _search_files(params: dict[str, Any]) -> dict[str, Any]:
        root = Path(str(params.get("root", Path.home()))).expanduser().resolve()
        pattern = str(params.get("pattern", "*"))
        limit = max(1, min(200, int(params.get("limit", 50))))
        matches = []
        for path in root.rglob(pattern):
            matches.append(str(path))
            if len(matches) >= limit:
                break
        return {"root": str(root), "matches": matches, "truncated": len(matches) >= limit}

    @staticmethod
    def _create_file(params: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(params["path"])).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(params.get("content", "")), encoding="utf-8")
        return {"path": str(path), "created": True}

    @classmethod
    def _open_app(cls, params: dict[str, Any]) -> dict[str, Any]:
        app = str(params.get("app", "")).lower()
        command = cls.APPS.get(app)
        if not command:
            raise ValueError("application is not allowlisted")
        subprocess.Popen(command, shell=False, creationflags=0x08000000 if sys.platform == "win32" else 0)
        return {"app": app, "opened": True}

    @staticmethod
    def _open_folder(params: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(params["path"])).expanduser().resolve()
        if not path.is_dir():
            raise NotADirectoryError(path)
        os.startfile(str(path))
        return {"path": str(path), "opened": True}

    @staticmethod
    def _switch_window(params: dict[str, Any]) -> dict[str, Any]:
        if sys.platform != "win32":
            raise RuntimeError("window switching is only available on Windows")
        needle = str(params.get("title", "")).lower()
        found: list[int] = []
        user32 = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def visit(handle: int, _lparam: int) -> bool:
            length = user32.GetWindowTextLengthW(handle)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, buffer, length + 1)
            if needle and needle in buffer.value.lower() and user32.IsWindowVisible(handle):
                found.append(handle)
                return False
            return True
        user32.EnumWindows(callback_type(visit), 0)
        if not found:
            raise LookupError("matching window not found")
        user32.SetForegroundWindow(found[0])
        return {"title": params.get("title", ""), "switched": True}

    @staticmethod
    def _screenshot(params: dict[str, Any]) -> dict[str, Any]:
        from PIL import ImageGrab
        path = Path(str(params.get("path", Path.cwd() / "screenshot.png"))).expanduser().resolve()
        if path.exists():
            raise FileExistsError("refusing to overwrite an existing screenshot without confirmation")
        path.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(all_screens=True).save(path)
        return {"path": str(path), "captured": True}

    def _copy_clipboard(self, params: dict[str, Any]) -> dict[str, Any]:
        text = str(params.get("text", ""))
        self.clipboard_writer(text)
        return {"characters": len(text), "copied": True}

    @staticmethod
    def _write_clipboard(text: str) -> None:
        if sys.platform != "win32":
            raise RuntimeError("clipboard writing is only available on Windows")
        subprocess.run(["clip.exe"], input=text, text=True, check=True,
                       creationflags=0x08000000)
