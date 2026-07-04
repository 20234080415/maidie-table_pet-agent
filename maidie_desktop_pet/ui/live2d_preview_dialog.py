from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QProcess, QUrl
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from animation.live2d_web import Live2DPreviewStatus, Live2DWebPreview
from animation.model_manager import AnimationModel


def build_load_model_script(model3_json: str | Path) -> str:
    model_url = QUrl.fromLocalFile(str(Path(model3_json).expanduser().resolve())).toString()
    return f"window.loadModel({json.dumps(model_url, ensure_ascii=False)})"


def preview_process_arguments(model: AnimationModel) -> list[str]:
    return [
        "-m", "ui.live2d_preview_process",
        "--name", model.name,
        "--model", str(Path(model.model3_json).resolve()),
    ]


class Live2DPreviewDialog(QDialog):
    """Status/control dialog for a crash-isolated WebEngine preview process."""

    def __init__(self, model: AnimationModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.preview_status = Live2DWebPreview().inspect(model, require_runtime=True)
        self.process: QProcess | None = None
        self.setWindowTitle(f"Live2D 预览状态 - {model.name}")
        self.resize(620, 300)
        layout = QVBoxLayout(self)
        title = QLabel(f"模型：{model.name}")
        title.setStyleSheet("font-size: 17px; font-weight: 600;")
        path = QLabel(f"model3.json：{model.model3_json}")
        path.setWordWrap(True)
        self.webengine_label = QLabel(
            "WebEngine：可用" if self.preview_status.code != "webengine_missing"
            else "WebEngine：未安装"
        )
        self.runtime_label = QLabel(
            "Runtime：文件齐全" if self.preview_status.code != "runtime_missing"
            else "Runtime：缺失"
        )
        self.status_label = QLabel(self.preview_status.message)
        self.status_label.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(path)
        layout.addWidget(self.webengine_label)
        layout.addWidget(self.runtime_label)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        close_button = QPushButton("关闭预览")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)
        if self.preview_status.available:
            self._start_preview_process()

    def _start_preview_process(self) -> None:
        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments(preview_process_arguments(self.model))
        process.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_process_output)
        process.readyReadStandardError.connect(self._read_process_error)
        process.errorOccurred.connect(self._on_process_error)
        process.finished.connect(self._on_process_finished)
        self.process = process
        self.status_label.setText("正在启动隔离的 Live2D WebEngine 预览…")
        process.start()

    def _read_process_output(self) -> None:
        if self.process is None:
            return
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in text.splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._apply_process_status(payload)

    def _read_process_error(self) -> None:
        if self.process is None:
            return
        text = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        if text:
            self.status_label.setText(f"预览进程错误：{text[-500:]}")

    def _apply_process_status(self, payload: dict[str, Any]) -> None:
        code = str(payload.get("code") or "")
        message = str(payload.get("message") or "")
        if code == "page_ready":
            self.webengine_label.setText("WebEngine：窗口已创建")
        if "runtimeFilesLoaded" in payload:
            self.runtime_label.setText(
                "Runtime：可用" if payload.get("runtimeFilesLoaded")
                else "Runtime：缺失或加载失败"
            )
        self.preview_status = Live2DPreviewStatus(
            bool(payload.get("ok")), message or "Live2D 预览状态未知。",
            self.model.name, self.model.model3_json, code or "preview_unknown", payload,
        )
        self.status_label.setText(self.preview_status.message)

    def _on_process_error(self, _error: QProcess.ProcessError) -> None:
        self.preview_status = Live2DPreviewStatus(
            False, "Live2D WebEngine 预览进程启动失败；Sprite 主程序不受影响。",
            self.model.name, self.model.model3_json, "preview_process_error",
        )
        self.status_label.setText(self.preview_status.message)

    def _on_process_finished(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        if status == QProcess.ExitStatus.CrashExit:
            message = (
                "Live2D WebEngine 预览进程发生原生崩溃；已隔离，Sprite 主程序不受影响。"
            )
            code = "preview_process_crashed"
        elif exit_code and self.preview_status.code not in {
            "runtime_missing", "model_load_failed", "loaded",
        }:
            message = f"Live2D 预览进程异常退出（exit={exit_code}）。"
            code = "preview_process_failed"
        else:
            return
        self.preview_status = Live2DPreviewStatus(
            False, message, self.model.name, self.model.model3_json, code,
            {"exit_code": exit_code},
        )
        self.status_label.setText(message)

    def closeEvent(self, event) -> None:
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1500):
                self.process.kill()
                self.process.waitForFinished(1000)
        super().closeEvent(event)


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
            False, f"创建 Live2D 预览状态窗口失败：{exc}", model.name,
            model.model3_json, "preview_creation_failed", {"error": str(exc)},
        )
        return None, failed.to_dict()
    return dialog, status.to_dict()
