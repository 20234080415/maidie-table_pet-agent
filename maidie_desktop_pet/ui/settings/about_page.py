from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

from core.version import (
    APP_AUTHOR, APP_DESCRIPTION, APP_GITHUB_URL, APP_NAME, APP_TECH_STACK, APP_VERSION,
)

class AboutPage(QWidget):
    """Application identity and capability summary."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        title = QLabel(APP_NAME)
        title.setObjectName("aboutAppName")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #704653;")
        version = QLabel(f"当前版本：{APP_VERSION}")
        version.setObjectName("aboutVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel(APP_DESCRIPTION)
        description.setObjectName("aboutDescription")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        details = QLabel(
            f"作者：{APP_AUTHOR}<br>技术栈：{APP_TECH_STACK}<br><br>"
            "Maidie 是一个行为驱动的 AI 桌面女仆，也是一个正在成长中的桌面 Agent。<br><br>"
            "<b>当前能力</b><br>桌宠动画 · 点击 / 拖拽 / 缩放 · 围栏与回弹<br>"
            "聊天气泡 · LLM 对话 · 工具调用 · 记忆系统<br>"
            "搜索工具 · OCR / Window 感知开发中"
        )
        details.setObjectName("aboutDetails")
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setWordWrap(True)
        github = QPushButton(f"GitHub（{APP_GITHUB_URL}）")
        github.setObjectName("githubButton")
        github.clicked.connect(self.open_github)
        changelog = QPushButton("更新日志（即将提供）")
        changelog.setObjectName("changelogPlaceholder")
        changelog.setEnabled(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(description)
        layout.addSpacing(8)
        layout.addWidget(details)
        layout.addStretch(1)
        layout.addWidget(github)
        layout.addWidget(changelog)

    def open_github(self) -> None:
        QDesktopServices.openUrl(QUrl(APP_GITHUB_URL))