from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from core.version import APP_AUTHOR, APP_DESCRIPTION, APP_NAME, APP_VERSION


class AboutPage(QWidget):
    """Application identity and capability summary."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        title = QLabel(APP_NAME)
        title.setObjectName("aboutAppName")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #704653;")
        version = QLabel(f"版本：v{APP_VERSION}")
        version.setObjectName("aboutVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel(APP_DESCRIPTION)
        description.setObjectName("aboutDescription")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        details = QLabel(
            f"作者：{APP_AUTHOR}<br>技术栈：Python + PyQt6 + LLM Agent<br><br>"
            "<b>当前能力</b><br>透明桌宠窗口 · 动画与鼠标互动 · 流式聊天<br>"
            "Agent 工具调用 · 屏幕与窗口感知 · 围栏模式<br>"
            "本地记忆 · 联网搜索 · 可扩展动作系统"
        )
        details.setObjectName("aboutDetails")
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setWordWrap(True)
        github = QPushButton("GitHub（链接待发布）")
        github.setObjectName("githubPlaceholder")
        github.setEnabled(False)
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
