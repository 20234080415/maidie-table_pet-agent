from __future__ import annotations

from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPoint, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QKeyEvent, QMouseEvent, QResizeEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QMessageBox,
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
    *, mode: str = "preview",
    pet_scale: float = 0.0,
    pet_offset_x: float = 0.0,
    pet_offset_y: float = 0.0,
    pet_align: str = "bottom",
    pet_bg: str = "transparent",
    fit_padding: float = 0.80,
    debug_fit: bool = False,
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
        window = Live2DPetWindow(model, parent, mode=mode,
                                 pet_scale=pet_scale,
                                 pet_offset_x=pet_offset_x,
                                 pet_offset_y=pet_offset_y,
                                 pet_align=pet_align,
                                 pet_bg=pet_bg,
                                 fit_padding=fit_padding,
                                 debug_fit=debug_fit)
    except Exception as exc:
        return None, {
            "ok": False, "code": "pet_window_creation_failed",
            "message": f"创建 Live2D 实验窗口失败：{exc}",
            "error": str(exc),
        }
    label = "桌宠" if mode == "pet" else "实验"
    return window, {"ok": True, "code": "pet_window_opened",
                    "message": f"Live2D {label}窗口已打开：{model.name}"}


class Live2DPetWindow(QWidget):
    """Experimental frameless Live2D pet window using QWebEngineView.

    This window embeds the Live2D viewer via HTTP server and uses the
    existing command transport layer (Live2DBackend → Live2DPreviewServer).
    """

    def __init__(self, model: AnimationModel, parent: QWidget | None = None,
                 *, mode: str = "preview",
                 pet_scale: float = 0.0,
                 pet_offset_x: float = 0.0,
                 pet_offset_y: float = 0.0,
                 pet_align: str = "bottom",
                 pet_bg: str = "transparent",
                 fit_padding: float = 0.80,
                 debug_fit: bool = False) -> None:
        super().__init__(parent)
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except ImportError as exc:
            raise RuntimeError(
                "未安装 PyQt6-WebEngine，无法创建 Live2D 实验窗口。"
            ) from exc
        except Exception as exc:
            message = str(exc)
            if "AA_ShareOpenGLContexts" in message or "QCoreApplication" in message:
                raise RuntimeError(
                    "QtWebEngine 初始化顺序错误：必须在 QApplication 创建之前 "
                    "导入 PyQt6.QtWebEngineWidgets 并设置 AA_ShareOpenGLContexts。"
                ) from exc
            raise

        self._model = model
        self._server: Live2DPreviewServer | None = None
        self._backend: Live2DBackend | None = None
        self._drag_start: QPoint | None = None
        self._scale = 1.0
        self._open_settings_callback: Callable[[], None] | None = None
        self._switch_to_sprite_callback: Callable[[], None] | None = None
        self._mode = mode if mode in ("preview", "pet") else "preview"
        self._is_pet = self._mode == "pet"
        self._pet_scale = float(pet_scale) if pet_scale else 0.0
        self._pet_offset_x = float(pet_offset_x) if pet_offset_x else 0.0
        self._pet_offset_y = float(pet_offset_y) if pet_offset_y else 0.0
        self._pet_align = str(pet_align or "bottom")
        self._pet_bg = str(pet_bg or "transparent")
        self._fit_padding = max(0.5, min(0.90, float(fit_padding or 0.80)))
        self._debug_fit = bool(debug_fit)
        self._embedded = False
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(120)
        self._fit_timer.timeout.connect(self.fit_to_view)

        title = "Live2D 桌宠" if self._is_pet else f"Live2D 实验预览 - {model.name}"
        self.setWindowTitle(f"Maidie {title}")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(420, 680) if self._is_pet else self.resize(700, 760)
        if self._is_pet:
            self.setMinimumSize(240, 360)

        self._webview = QWebEngineView(self)
        self._webview.setMinimumSize(200, 260) if self._is_pet else self._webview.setMinimumSize(300, 300)
        self._configure_webengine_background()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._webview, 1)

        if not self._is_pet:
            self._debug_bar = self._build_debug_bar()
            layout.addWidget(self._debug_bar)
        else:
            self._debug_bar = None

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

    def _configure_webengine_background(self) -> None:
        page = self._webview.page()
        if hasattr(page, "backgroundColorChanged"):
            page.backgroundColorChanged.connect(self._on_bg_changed)
        try:
            if hasattr(page, "setBackgroundColor"):
                from PyQt6.QtGui import QColor
                page.setBackgroundColor(QColor(0, 0, 0, 0))
        except Exception:
            pass

    def _on_bg_changed(self) -> None:
        pass

    def _start_server(self) -> None:
        self._server = Live2DPreviewServer(self._model, viewer=viewer_root(),
                                           lifetime_seconds=0)
        self._server.start()
        url = self._server.viewer_url(mode=self._mode)
        if self._is_pet:
            params = []
            if self._pet_scale > 0:
                params.append(f"petScale={self._pet_scale}")
            if self._pet_offset_x != 0:
                params.append(f"petOffsetX={self._pet_offset_x}")
            if self._pet_offset_y != 0:
                params.append(f"petOffsetY={self._pet_offset_y}")
            if self._pet_align != "bottom":
                params.append(f"petAlign={self._pet_align}")
            if self._pet_bg and self._pet_bg != "transparent":
                params.append(f"bg={self._pet_bg.replace('#', '%23')}")
            params.append(f"fitPadding={self._fit_padding}")
            if self._debug_fit:
                params.append("debugFit=1")
            if params:
                url += "&" + "&".join(params)
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

    def set_embedded(self, embedded: bool) -> None:
        self._embedded = bool(embedded)
        if self._embedded:
            self._webview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._webview.customContextMenuRequested.connect(self._show_embedded_context_menu)

    def _show_embedded_context_menu(self, position: QPoint) -> None:
        parent = self.parentWidget()
        if parent is None or not hasattr(parent, "_build_context_menu"):
            return
        parent._build_context_menu().exec(self._webview.mapToGlobal(position))

    def fit_to_view(self) -> None:
        self._webview.page().runJavaScript(
            "window.fitModelToView ? window.fitModelToView() : null"
        )

    def reset_display(self) -> dict[str, Any]:
        if self._backend is None:
            return {"ok": False, "code": "no_backend", "message": "后端未初始化。"}
        return self._backend.reset_view()

    def set_callbacks(
        self,
        open_settings: Callable[[], None] | None = None,
        switch_to_sprite: Callable[[], None] | None = None,
    ) -> None:
        self._open_settings_callback = open_settings
        self._switch_to_sprite_callback = switch_to_sprite

    def contextMenuEvent(self, event) -> None:
        if event is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #2a2e37; color: #e0e0e0; border: 1px solid #78dfff; "
            "padding: 4px; } "
            "QMenu::item { padding: 6px 24px; } "
            "QMenu::item:selected { background: #3a5060; }"
        )
        settings_action = QAction("打开设置", menu)
        settings_action.triggered.connect(self._handle_open_settings)
        menu.addAction(settings_action)

        sprite_action = QAction("切回 Sprite", menu)
        sprite_action.triggered.connect(self._handle_switch_to_sprite)
        menu.addAction(sprite_action)

        menu.addSeparator()

        close_action = QAction("关闭 Live2D 窗口", menu)
        close_action.triggered.connect(self.close)
        menu.addAction(close_action)

        menu.exec(event.globalPos())

    def _handle_open_settings(self) -> None:
        if self._open_settings_callback is not None:
            self._open_settings_callback()
        else:
            QMessageBox.information(
                self, "未配置", "设置入口未配置，请通过其他方式打开设置。"
            )

    def _handle_switch_to_sprite(self) -> None:
        if self._switch_to_sprite_callback is not None:
            self._switch_to_sprite_callback()
        else:
            QMessageBox.information(
                self, "未配置", "切回 Sprite 功能未配置，请手动修改配置文件。"
            )

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
        if self._embedded:
            parent = self.parentWidget()
            if parent is not None and hasattr(parent, "scale_window"):
                parent.scale_window(factor)
            self._fit_timer.start()
            event.accept()
            return
        self._scale = max(0.3, min(2.5, self._scale * factor))
        base_w, base_h = (420, 680) if self._is_pet else (700, 760)
        new_w = int(base_w * self._scale)
        new_h = int(base_h * self._scale)
        self.resize(new_w, new_h)
        super().wheelEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_timer.start()

    def closeEvent(self, event) -> None:
        self._fit_timer.stop()
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
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() in (Qt.Key.Key_Q, Qt.Key.Key_W):
                self.close()
                return
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
