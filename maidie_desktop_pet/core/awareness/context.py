"""聚合窗口、鼠标、空闲、应用和剪贴板的本地 Awareness 状态。

``PetController``/ScreenTool 通过单一快照接口读取环境信息，避免 Brain 直接依赖多个
Tracker；聚合层不扩大采集范围，也不把数据自动发送到网络服务。
"""

from __future__ import annotations

from typing import Any


class AwarenessContext:
    """多个 Awareness Tracker 的只读聚合门面。

    实例随桌宠运行期常驻并引用各 Tracker；``snapshot`` 用于体验层，
    ``screen_awareness_snapshot`` 是 Vision 不可用时的结构化降级来源。
    """
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
            "screen_text": "", "context": "unknown", "status": "unavailable",
            "error": "screen reader is unavailable", "error_code": "screen_reader_unavailable",
            "screenshot_source": "failed", "ocr_enabled": False, "ocr_text_length": 0,
        }
        app = self.app_tracker.snapshot() if self.app_tracker else {
            "active_app": "unknown", "app_type": "unknown"
        }
        window = self.window_tracker.snapshot()
        ignored_self = bool(window.get("ignored_self_window", False))
        if ignored_self:
            app = {
                "active_app": str(window.get("process_name") or "unknown"),
                "app_type": str(window.get("window_state") or "unknown"),
            }
        candidates = (
            str(app.get("app_type", "unknown")),
            str(window.get("window_state", "unknown")),
            str(screen.get("context", "unknown")),
        )
        aliases = {"chat": "chatting", "browser": "browsing"}
        context = next((aliases.get(value, value) for value in candidates
                        if aliases.get(value, value) in {"coding", "browsing", "chatting"}), "unknown")
        result = {
            "screen_text": str(screen.get("screen_text", "")),
            "app": str(app.get("active_app", "unknown")),
            "window": str(window.get("window_title", "")),
            "context": context,
            "screen_debug": {
                "intent": "screen",
                "active_window": str(window.get("window_title", "")),
                "ignored_self_window": ignored_self,
                "screenshot_source": str(screen.get("screenshot_source", "failed")),
                "ocr_enabled": bool(screen.get("ocr_enabled", False)),
                "ocr_text_length": int(screen.get("ocr_text_length", 0)),
            },
            "tool_status": {
                "screen_ocr": str(screen.get("status", "ok")),
                "app_tracker": "ok",
                "window_tracker": str(window.get("error", "ok")),
            },
        }
        if screen.get("error"):
            result.update({"error": str(screen["error"]),
                           "error_code": str(screen.get("error_code", "screen_read_failed"))})
        elif window.get("error"):
            result.update({"error": "No external foreground window was available",
                           "error_code": "no_external_window"})
        return result
