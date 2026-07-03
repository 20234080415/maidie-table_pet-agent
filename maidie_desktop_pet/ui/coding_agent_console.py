from __future__ import annotations

from collections import deque
from time import monotonic

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout


class CodingAgentConsole(QDialog):
    STATUS_TEXT = {"running": "运行中", "completed": "已完成", "cancelled": "已取消",
                   "timeout": "超时", "idle_timeout": "无输出超时",
                   "needs_setup": "等待配置", "failed": "失败"}

    def __init__(self, cancel_callback, parent=None) -> None:
        super().__init__(parent)
        self.cancel_callback = cancel_callback
        self.lines: deque[str] = deque(maxlen=200)
        self.started_at = 0.0
        self.last_output_at = 0.0
        self.setWindowTitle("OpenCode Console / Coding Agent Console")
        self.resize(620, 360)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Tool)
        self.setStyleSheet("QDialog{background:#171b22;color:#b8f7c7} QTextEdit{background:#0b0e12;color:#9ef0b1;font-family:Consolas;border:1px solid #3c7650} QPushButton{padding:5px 10px}")
        self.status = QLabel("状态：待机")
        self.elapsed = QLabel("已运行：0 秒")
        self.last_output = QLabel("最近输出：—")
        top = QHBoxLayout(); top.addWidget(self.status); top.addStretch(); top.addWidget(self.elapsed); top.addWidget(self.last_output)
        self.output = QTextEdit(); self.output.setReadOnly(True)
        cancel = QPushButton("取消"); cancel.clicked.connect(cancel_callback)
        clear = QPushButton("清空"); clear.clicked.connect(self.clear)
        copy = QPushButton("复制日志"); copy.clicked.connect(self.copy_log)
        bottom = QHBoxLayout(); bottom.addStretch(); bottom.addWidget(cancel); bottom.addWidget(clear); bottom.addWidget(copy)
        layout = QVBoxLayout(self); layout.addLayout(top); layout.addWidget(self.output); layout.addLayout(bottom)
        self.timer = QTimer(self); self.timer.setInterval(1000); self.timer.timeout.connect(self._tick)

    def handle_event(self, event: dict) -> None:
        kind = event.get("event")
        if kind == "start":
            self.started_at = self.last_output_at = monotonic(); self.lines.clear(); self.output.clear()
            self._set_status("running"); self.show(); self.raise_(); self.timer.start()
        elif kind == "output":
            self.last_output_at = monotonic()
            full = f"[{event.get('stream', 'stdout')}] {event.get('line', '')}"
            self.lines.append(full)
            shown = full if len(full) <= 500 else full[:500] + " …[截断]"
            self.output.append(shown)
        elif kind in {"status", "finish"}:
            self._set_status(str(event.get("status") or "failed"))
            if kind == "finish": self.timer.stop()
        self._tick()

    def _set_status(self, status: str) -> None:
        self.status.setText("状态：" + self.STATUS_TEXT.get(status, status))

    def _tick(self) -> None:
        now = monotonic()
        if self.started_at: self.elapsed.setText(f"已运行：{int(now-self.started_at)} 秒")
        if self.last_output_at: self.last_output.setText(f"最近输出：{int(now-self.last_output_at)} 秒前")

    def clear(self) -> None:
        self.lines.clear(); self.output.clear()

    def copy_log(self) -> None:
        QGuiApplication.clipboard().setText("\n".join(self.lines))
