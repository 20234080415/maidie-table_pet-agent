from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlsplit

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)


class LongResponsePanel(QDialog):
    """Scrollable, personality-neutral presentation for long results."""

    LONG_DISPLAY_TYPES = {
        "long_response", "tool_result", "coding_analysis", "search_result",
    }
    SECTION_TITLES = {
        "project_overview": "项目概览",
        "key_findings": "优先问题",
        "priority_suggestions": "优先建议",
        "validation_suggestions": "验证建议",
        "cautions": "注意事项",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.setWindowTitle("详细结果")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumWidth(420)
        self.setMaximumWidth(560)
        self.resize(520, 420)
        self.setMaximumHeight(500)
        self.setStyleSheet(
            "QDialog{background:#f5e9ec;color:#49343d;}"
            "QLabel#panelTitle{font-size:17px;font-weight:600;padding:5px;}"
            "QTextBrowser{background:#fffafb;color:#3f3036;border:1px solid #d4adb8;"
            "border-radius:10px;padding:12px;font-size:14px;}"
            "QPushButton{background:#d9a8b6;color:#3f2d34;border:1px solid #c38b9c;"
            "border-radius:8px;padding:6px 14px;}"
        )

        self.title_label = QLabel("详细结果")
        self.title_label.setObjectName("panelTitle")
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.copy_button = QPushButton("复制")
        self.copy_button.clicked.connect(self.copy_full_content)
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.hide)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.browser, stretch=1)
        layout.addLayout(buttons)

    @classmethod
    def should_show(cls, response: dict[str, Any]) -> bool:
        display_type = str(response.get("display_type") or "")
        if display_type in cls.LONG_DISPLAY_TYPES:
            return True
        text = str(response.get("full_text") or response.get("text") or "")
        list_lines = sum(
            1 for line in text.splitlines()
            if line.lstrip().startswith(("- ", "* ", "• "))
        )
        return len(text) > 160 or list_lines >= 2

    def show_result(
        self, title: str, content: dict[str, Any] | None = None,
        full_text: str = "", anchor: QRect | None = None,
        screen: QRect | None = None,
        sources: list[dict[str, Any]] | None = None,
        show_sources: bool = False,
    ) -> None:
        self.setWindowTitle(title or "详细结果")
        self.title_label.setText(title or "详细结果")
        self._full_text = full_text or self._content_text(content or {})
        safe_sources = self._safe_sources(sources or []) if show_sources else []
        if safe_sources:
            self.browser.setHtml(self._result_html(self._full_text, safe_sources))
        else:
            self.browser.setPlainText(self._full_text)
        self.show()
        if anchor is not None and screen is not None:
            self.position_near(anchor, screen)
        self.raise_()
        self.activateWindow()

    def position_near(self, anchor: QRect, screen: QRect) -> None:
        gap = 10
        left_x = anchor.left() - self.width() - gap
        right_x = anchor.right() + gap
        x = left_x if left_x >= screen.left() else right_x
        x = max(screen.left(), min(screen.right() - self.width() + 1, x))
        y = anchor.center().y() - self.height() // 2
        y = max(screen.top(), min(screen.bottom() - self.height() + 1, y))
        self.move(x, y)

    def copy_full_content(self) -> None:
        QGuiApplication.clipboard().setText(self._full_text)

    def _content_text(self, content: dict[str, Any]) -> str:
        sections: list[str] = []
        for key, title in self.SECTION_TITLES.items():
            value = content.get(key)
            if not value:
                continue
            if isinstance(value, list):
                body = "\n".join(f"- {item}" for item in value if str(item).strip())
            else:
                body = str(value).strip()
            if body:
                sections.append(f"{title}\n{body}")
        return "\n\n".join(sections)

    @staticmethod
    def _safe_sources(sources: list[dict[str, Any]]) -> list[dict[str, str]]:
        safe: list[dict[str, str]] = []
        for source in sources:
            if not isinstance(source, dict):
                continue
            url = str(source.get("url") or "").strip()
            try:
                parsed = urlsplit(url)
            except ValueError:
                continue
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                continue
            domain = str(source.get("domain") or parsed.hostname).strip()
            safe.append({
                "title": str(source.get("title") or domain or url),
                "url": url,
                "domain": domain,
            })
        return safe

    @staticmethod
    def _result_html(text: str, sources: list[dict[str, str]]) -> str:
        body = escape(text).replace("\n", "<br>")
        links = []
        for source in sources:
            title = escape(source["title"])
            url = escape(source["url"], quote=True)
            domain = escape(source["domain"])
            suffix = f" <span>({domain})</span>" if domain else ""
            links.append(f'<li><a href="{url}">{title}</a>{suffix}</li>')
        return f"<p>{body}</p><hr><h3>来源</h3><ol>{''.join(links)}</ol>"
