from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPoint, Qt, QUrl
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from animation.live2d_backend import Live2DBackend
from animation.live2d_preview_server import Live2DPreviewServer
from animation.live2d_web import viewer_root
from animation.model_manager import AnimationModel

WEBENGINE_AVAILABLE = find_spec("PyQt6.QtWebEngineWidgets") is not None


def pet_window_available() -> bool:
    return WEBENGINE_AVAILABLE


def create_live2d_pet_window(
    model: AnimationModel | None, parent: QWidget | None = None,
) -> tuple[QWidget | None, dict[str, Any]]:
    if model is None:
        return None, {
            "ok": False, "code": "model_not_selected",
            "message": "未选择有效的 Live2D 模型。",
        }
    model_path = Path(model.model3_json)
    if not model_path.is_file():
        return None, {
            "ok": False, "code": "model_missing",
            "message": "Live2D model3_json 不存在。",
            "model3_json": model.model3_json,
        }
    if not WEBENGINE_AVAILABLE:
        return None, {
            "ok": False, "code": "webengine_missing",
            "message": "未安装 PyQt6-WebEngine，无法创建 Live2D 实验窗口。可使用浏览器预览代替。",
        }
    viewer = viewer_root()
    if not viewer.joinpath("index.html").is_file():
        return None, {
            "ok": False, "code": "viewer_missing",
            "message": "Live2D viewer/index.html 不存在。",
        }
    try:
        window = Live2DPetWindow(model, parent)
    except Exception as exc:
        return None, {
            "ok": False, "code": "pet_window_creation_failed",
            "message": f"创建 Live2D 实验窗口失败：{exc}",
            "error": str(exc),
        }
    return window, {"ok": True, "code": "pet_window_opened",
                    "message": f"Live2D 实验窗口已打开：{model.name}"}


class Live2DPetWindow(QWidget):
    """Experimental frameless Live2D pet window using QWebEngineView.

    This window embeds the Live2D viewer via HTTP server and uses the
    existing command transport layer (Live2DBackend → Live2DPreviewServer).
    """

    def __init__(self, model: AnimationModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        self._model = model
        self._server: Live2DPreviewServer | None = None
        self._backend: Live2DBackend | None = None
        self._drag_start: QPoint | None = None
        self._scale = 1.0

        self.setWindowTitle(f"Maidie Live2D 实验桌宠 - {model.name}")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(600, 700)

        self._webview = QWebEngineView(self)
        self._webview.setMinimumSize(300, 300)
        self._webview.page().backgroundColorChanged.connect(self._on_bg_changed)

        self._debug_bar = self._build_debug_bar()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._webview, 1)
        layout.addWidget(self._debug_bar)

        self._start_server()

    def _build_debug_bar(self) -> QWidget:
        bar = QWidget(self)
        bar.setFixedHeight(36)
        bar.setStyleSheet("background: rgba(31, 34, 40, 0.92); padding: 2px;")
        hlayout = QHBoxLayout(bar)
        hlayout.setContentsMargins(4, 2, 4, 2)
        hlayout.setSpacing(4)

        for state in ("idle", "speaking", "confused", "success", "error"):
            btn = QPushButton(state)
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                "background: #263a47; color: #e0e0e0; border: 1px solid #78dfff; "
                "border-radius: 4px; padding: 2px 8px; font-size: 11px;"
            )
            btn.clicked.connect(lambda _checked, s=state: self.test_state(s))
            hlayout.addWidget(btn)

        close_btn = QPushButton("x")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "background: #5a2e3a; color: #ff9eae; border: 1px solid #c96b7a; "
            "border-radius: 4px; font-weight: bold; font-size: 12px;"
        )
        close_btn.clicked.connect(self.close)
        hlayout.addWidget(close_btn)
        return bar

    def _on_bg_changed(self) -> None:
        pass

    def _start_server(self) -> None:
        self._server = Live2DPreviewServer(self._model, viewer=viewer_root(),
                                           lifetime_seconds=0)
        url = self._server.start()
        self._backend = Live2DBackend(
            command_sink=lambda cmd: self._server.enqueue_command(
                self._server.session_id, cmd) if self._server else False
        )
        self._webview.setUrl(QUrl(url))

    def test_state(self, state: str) -> dict[str, Any]:
        if self._backend is None:
            return {"ok": False, "code": "no_backend", "message": "后端未初始化。"}
        return self._backend.apply_state(state)

    def current_backend(self) -> Live2DBackend | None:
        return self._backend

    def current_server(self) -> Live2DPreviewServer | None:
        return self._server

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        self._drag_start = None
        if event is not None:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is None:
            return
        delta = event.angleDelta().y()
        factor = 1.05 if delta > 0 else 0.95
        self._scale = max(0.3, min(2.5, self._scale * factor))
        new_w = int(600 * self._scale)
        new_h = int(700 * self._scale)
        self.resize(new_w, new_h)
        super().wheelEvent(event)

    def closeEvent(self, event) -> None:
        if self._backend is not None:
            self._backend.shutdown()
            self._backend = None
        if self._server is not None:
            self._server.stop()
            self._server = None
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            return
        if int(event.modifiers()) & int(Qt.KeyboardModifier.ControlModifier):
            if event.key() in (Qt.Key.Key_Q, Qt.Key.Key_W):
                self.close()
                return
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
