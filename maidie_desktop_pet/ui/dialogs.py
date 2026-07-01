from __future__ import annotations

import html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.settings import PERSONALITY_PRESETS


BASE_STYLE = """
QDialog { background: #fff8fb; color: #4a2938; }
QLabel { color: #5b3547; }
QLineEdit, QTextEdit, QComboBox, QTextBrowser {
  background: #fffdfd; color: #452735; border: 1px solid #e2a7bf;
  border-radius: 8px; padding: 6px; selection-background-color: #e7a7c2;
}
QPushButton { background: #f3c5d7; color: #4a2938; border: none;
  border-radius: 8px; padding: 7px 14px; }
QPushButton:hover { background: #ebb1c9; }
QTabWidget::pane { border: 1px solid #edc3d3; border-radius: 8px; }
"""


class RecentChatsDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Maidie 的最近聊天")
        self.resize(460, 430)
        self.setStyleSheet(BASE_STYLE)
        self.browser = QTextBrowser()
        clear_button = QPushButton("清除聊天记录")
        clear_button.clicked.connect(self._clear)
        layout = QVBoxLayout(self)
        layout.addWidget(self.browser)
        layout.addWidget(clear_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.refresh()

    def refresh(self) -> None:
        items = self.controller.recent_chats()
        if not items:
            self.browser.setHtml("<p style='color:#9b7284;text-align:center'>还没有聊天记录。</p>")
            return
        parts = []
        for item in items:
            when = html.escape(str(item.get("time", "")))
            message = html.escape(str(item.get("message", "")))
            response = html.escape(str(item.get("response", "")))
            parts.append(
                f"<div style='margin:8px 2px 14px'>"
                f"<small style='color:#a0798a'>{when}</small>"
                f"<p><b>你：</b>{message}</p>"
                f"<p style='background:#fff0f5;padding:8px;border-radius:9px'>"
                f"<b>Maidie：</b>{response}</p></div>"
            )
        self.browser.setHtml("".join(parts))

    def _clear(self) -> None:
        self.controller.clear_memory()
        self.refresh()


class SettingsDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.settings = controller.settings_snapshot()
        self.setWindowTitle("Maidie 性格与模型")
        self.resize(500, 420)
        self.setStyleSheet(BASE_STYLE)

        tabs = QTabWidget()
        tabs.addTab(self._build_personality_tab(), "性格")
        tabs.addTab(self._build_model_tab(), "模型与 API")
        tabs.addTab(self._build_network_tab(), "联网查询")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存并立即应用")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def _build_personality_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.personality = QComboBox()
        for key, (label, _description) in PERSONALITY_PRESETS.items():
            self.personality.addItem(label, key)
        current = self.personality.findData(self.settings.get("personality_preset"))
        self.personality.setCurrentIndex(max(0, current))
        self.personality.currentIndexChanged.connect(self._update_personality_help)
        self.personality_help = QLabel()
        self.personality_help.setWordWrap(True)
        self.custom_personality = QTextEdit()
        self.custom_personality.setPlaceholderText("例如：更黏人一点，喜欢用轻松的短句安慰主人……")
        self.custom_personality.setPlainText(self.settings.get("custom_personality", ""))
        self.custom_personality.setMaximumHeight(120)
        layout.addRow("性格预设", self.personality)
        layout.addRow("性格说明", self.personality_help)
        layout.addRow("自定义性格", self.custom_personality)
        self._update_personality_help()
        return page

    def _update_personality_help(self) -> None:
        key = self.personality.currentData()
        self.personality_help.setText(PERSONALITY_PRESETS[key][1] or "使用下面填写的自定义性格。")
        self.custom_personality.setEnabled(key == "custom")

    def _build_model_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.provider = QComboBox()
        self.provider.addItem("DeepSeek", "deepseek")
        self.provider.addItem("其他 OpenAI 兼容接口", "custom")
        index = self.provider.findData(self.settings.get("provider", "deepseek"))
        self.provider.setCurrentIndex(max(0, index))
        self.base_url = QLineEdit(self.settings.get("base_url", "https://api.deepseek.com"))
        self.chat_model = QLineEdit(self.settings.get("chat_model", "deepseek-v4-flash"))
        self.technical_model = QLineEdit(self.settings.get("technical_model", "deepseek-v4-pro"))
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText(
            "已配置；留空保持不变" if self.settings.get("has_api_key") else "输入 API Key"
        )
        note = QLabel("Key 以密码形式输入。若系统设置了 DEEPSEEK_API_KEY，环境变量优先。")
        note.setWordWrap(True)
        layout.addRow("接口类型", self.provider)
        layout.addRow("Base URL", self.base_url)
        layout.addRow("聊天模型", self.chat_model)
        layout.addRow("技术模型", self.technical_model)
        layout.addRow("API Key", self.api_key)
        layout.addRow("", note)
        return page

    def _build_network_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.network_enabled = QCheckBox("允许 Maidie 按当前问题联网查询")
        self.network_enabled.setChecked(self.settings.get("network_enabled", False))
        self.network_provider = QComboBox()
        self.network_provider.addItem("Tavily", "tavily")
        index = self.network_provider.findData(
            self.settings.get("network_search_provider", "tavily")
        )
        self.network_provider.setCurrentIndex(max(0, index))
        self.network_api_key = QLineEdit()
        self.network_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.network_api_key.setPlaceholderText(
            "已配置；留空保持不变"
            if self.settings.get("has_network_api_key") else "输入 Tavily API Key"
        )
        self.network_timeout = QSpinBox()
        self.network_timeout.setRange(1, 120)
        self.network_timeout.setSuffix(" 秒")
        self.network_timeout.setValue(self.settings.get("network_timeout", 10))
        self.network_show_sources = QCheckBox("在回答中显示来源")
        self.network_show_sources.setChecked(
            self.settings.get("network_show_sources", True)
        )
        note = QLabel("联网默认关闭。开启后，只会把当前问题发送给所选搜索服务。")
        note.setWordWrap(True)
        layout.addRow("联网开关", self.network_enabled)
        layout.addRow("搜索服务", self.network_provider)
        layout.addRow("搜索 API Key", self.network_api_key)
        layout.addRow("请求超时", self.network_timeout)
        layout.addRow("来源", self.network_show_sources)
        layout.addRow("", note)
        return page

    def _save(self) -> None:
        values = {
            "provider": self.provider.currentData(),
            "base_url": self.base_url.text().strip(),
            "chat_model": self.chat_model.text().strip(),
            "technical_model": self.technical_model.text().strip(),
            "api_key": self.api_key.text().strip(),
            "personality_preset": self.personality.currentData(),
            "custom_personality": self.custom_personality.toPlainText().strip(),
            "network_enabled": self.network_enabled.isChecked(),
            "network_timeout": self.network_timeout.value(),
            "network_show_sources": self.network_show_sources.isChecked(),
            "network_search_provider": self.network_provider.currentData(),
            "network_search_api_key": self.network_api_key.text().strip(),
        }
        if not values["base_url"] or not values["chat_model"] or not values["technical_model"]:
            return
        self.controller.apply_settings(values)
        self.accept()
