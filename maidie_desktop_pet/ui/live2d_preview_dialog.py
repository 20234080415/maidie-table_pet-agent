from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from animation.live2d_web import Live2DPreviewStatus, Live2DWebPreview, viewer_root
from animation.model_manager import AnimationModel


def _import_webengine():
    """Keep the optional package out of normal Maidie imports."""
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    return QWebEngineView, QWebEngineSettings


class Live2DPreviewDialog(QDialog):
    """Independent preview only; closing it never touches the pet window."""

    def __init__(self, model: AnimationModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.preview_status = Live2DWebPreview().inspect(model, require_runtime=True)
        self.web_view = None
        self.setWindowTitle(f"Live2D 预览 - {model.name}")
        self.resize(720, 760)
        layout = QVBoxLayout(self)
        title = QLabel(f"模型：{model.name}")
        title.setStyleSheet("font-size: 17px; font-weight: 600;")
        path = QLabel(f"model3.json：{model.model3_json}")
        path.setWordWrap(True)
        self.status_label = QLabel(self.preview_status.message)
        self.status_label.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(path)
        layout.addWidget(self.status_label)

        if self.preview_status.available:
            self._create_web_view(layout)
        else:
            placeholder = QLabel(
                "预览未启动。主桌宠继续使用 Sprite，不受此窗口影响。"
            )
            placeholder.setAlignment(placeholder.alignment())
            placeholder.setMinimumHeight(420)
            placeholder.setWordWrap(True)
            layout.addWidget(placeholder, 1)
        close_button = QPushButton("关闭预览")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)

    def _create_web_view(self, layout: QVBoxLayout) -> None:
        try:
            view_class, settings_class = _import_webengine()
            view = view_class(self)
            settings = view.settings()
            settings.setAttribute(
                settings_class.WebAttribute.LocalContentCanAccessFileUrls, True
            )
            settings.setAttribute(
                settings_class.WebAttribute.LocalContentCanAccessRemoteUrls, False
            )
            view.loadFinished.connect(self._on_load_finished)
            view.setUrl(QUrl.fromLocalFile(str((viewer_root() / "index.html").resolve())))
            self.web_view = view
            layout.addWidget(view, 1)
        except Exception as exc:
            self.preview_status = Live2DPreviewStatus(
                False, f"创建 WebEngine 预览失败：{exc}", self.model.name,
                self.model.model3_json, "preview_creation_failed",
                {"error": str(exc)},
            )
            self.status_label.setText(self.preview_status.message)

    def _on_load_finished(self, ok: bool) -> None:
        if not ok or self.web_view is None:
            self.preview_status = Live2DPreviewStatus(
                False, "Live2D viewer 页面加载失败。", self.model.name,
                self.model.model3_json, "viewer_load_failed",
            )
            self.status_label.setText(self.preview_status.message)
            return
        model_url = QUrl.fromLocalFile(str(Path(self.model.model3_json).resolve())).toString()
        script = f"window.loadModel({model_url!r})"
        self.web_view.page().runJavaScript(script, self._on_model_result)

    def _on_model_result(self, result: Any) -> None:
        payload = result if isinstance(result, dict) else {}
        if payload.get("ok") and payload.get("code") == "loading":
            self.preview_status = Live2DPreviewStatus(
                True, "Live2D 模型正在异步加载；最终状态会显示在预览页面中。",
                self.model.name, self.model.model3_json, "loading",
            )
        elif payload.get("ok"):
            self.preview_status = Live2DPreviewStatus(
                True, "Live2D 模型已加载。", self.model.name,
                self.model.model3_json, "loaded",
            )
        else:
            message = str(payload.get("message") or "Live2D 模型加载失败。")
            self.preview_status = Live2DPreviewStatus(
                False, message, self.model.name, self.model.model3_json,
                str(payload.get("code") or "model_load_failed"), payload,
            )
        self.status_label.setText(self.preview_status.message)

    def set_expression(self, name: str) -> None:
        if self.web_view is not None:
            self.web_view.page().runJavaScript(f"window.setExpression({name!r})")

    def set_parameter(self, name: str, value: float) -> None:
        if self.web_view is not None:
            self.web_view.page().runJavaScript(
                f"window.setParameter({name!r}, {float(value)!r})"
            )


def create_live2d_preview_dialog(
    model: AnimationModel | None, parent: QWidget | None = None,
) -> tuple[Live2DPreviewDialog | None, dict[str, Any]]:
    if model is None:
        status = Live2DPreviewStatus(
            False, "未选择有效的 Live2D 模型。", code="model_not_selected"
        )
        return None, status.to_dict()
    status = Live2DWebPreview().inspect(model, require_runtime=True)
    try:
        dialog = Live2DPreviewDialog(model, parent)
    except Exception as exc:
        failed = Live2DPreviewStatus(
            False, f"创建 Live2D 预览窗口失败：{exc}", model.name,
            model.model3_json, "preview_creation_failed", {"error": str(exc)},
        )
        return None, failed.to_dict()
    return dialog, status.to_dict()
