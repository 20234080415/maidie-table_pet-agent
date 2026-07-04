from __future__ import annotations

import html

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.settings import PERSONALITY_PRESETS
from animation.live2d_web import Live2DWebPreview
from animation.live2d_preview_server import open_browser_preview
from animation.model_manager import AnimationModelRegistry
from ui.live2d_preview_dialog import create_live2d_preview_dialog
from core.tools.coding_agent_tool import CodingAgentTool
from core.tools.coding_agent_installer import CodingAgentInstaller


BASE_STYLE = """
QDialog, QWidget {
  background: #f1e4e7;
  color: #49343d;
}
QLabel, QCheckBox { color: #574049; }
QLineEdit, QTextEdit, QComboBox, QTextBrowser, QSpinBox {
  background: #f8eef0;
  color: #3f3036;
  border: 1px solid #cfaab4;
  border-radius: 8px;
  padding: 6px;
  selection-background-color: #c98fa1;
  selection-color: #2e2025;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
  background: #faF2f3;
  border: 1px solid #b9798d;
}
QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
  background: #e6d8dc;
  color: #89747b;
}
QPushButton {
  background: #d9a8b6;
  color: #3f2d34;
  border: 1px solid #c38b9c;
  border-radius: 8px;
  padding: 7px 14px;
}
QPushButton:hover { background: #ce96a7; }
QPushButton:pressed { background: #bf8497; }
QTabWidget::pane {
  background: #eadadd;
  border: 1px solid #cda6b1;
  border-radius: 8px;
  top: -1px;
}
QTabBar::tab {
  background: #dfc9cf;
  color: #634852;
  border: 1px solid #cba7b1;
  padding: 7px 12px;
  margin-right: 2px;
  border-top-left-radius: 7px;
  border-top-right-radius: 7px;
}
QTabBar::tab:selected { background: #eadadd; color: #3f2d34; }
"""


class _OpenCodeInstallWorker(QObject):
    finished = pyqtSignal(dict)

    def __init__(self, installer: CodingAgentInstaller, method: str) -> None:
        super().__init__()
        self.installer = installer
        self.method = method

    @pyqtSlot()
    def run(self) -> None:
        self.finished.emit(self.installer.install_opencode(self.method))


class _Live2DScanWorker(QObject):
    finished = pyqtSignal(object)

    def __init__(self, root: str) -> None:
        super().__init__()
        self.root = root

    @pyqtSlot()
    def run(self) -> None:
        try:
            registry = AnimationModelRegistry()
            models = [model.to_dict() for model in registry.scan_model_root(self.root)]
            self.finished.emit({"ok": True, "models": models})
        except Exception as exc:
            self.finished.emit({"ok": False, "models": [], "error": str(exc)})


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
    def __init__(self, controller, parent=None, initial_tab: str | None = None):
        super().__init__(parent)
        self.controller = controller
        self.settings = controller.settings_snapshot()
        self.coding_agent_installer = CodingAgentInstaller(timeout_seconds=300)
        self._install_thread: QThread | None = None
        self._install_worker: _OpenCodeInstallWorker | None = None
        self._live2d_scan_thread: QThread | None = None
        self._live2d_scan_worker: _Live2DScanWorker | None = None
        self.live2d_registry = AnimationModelRegistry(
            self.settings.get("animation_live2d_models", []),
            self.settings.get("animation_current_model_id", ""),
        )
        self.live2d_preview = Live2DWebPreview()
        self._live2d_preview_windows: list[QDialog] = []
        self._live2d_preview_servers: list[object] = []
        self.setWindowTitle("Maidie 设置")
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.WindowStaysOnTopHint
        flags |= Qt.WindowType.WindowMinimizeButtonHint
        self.setWindowFlags(flags)
        self.resize(720, 540)
        self.setStyleSheet(BASE_STYLE)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_personality_tab(), "性格")
        self.tabs.addTab(self._build_model_tab(), "模型与 API")
        self.tabs.addTab(self._build_animation_tab(), "动画 / Live2D")
        self.tabs.addTab(self._build_network_tab(), "联网查询")
        self.tabs.addTab(self._build_vision_tab(), "千问视觉")
        self.tabs.addTab(self._build_coding_agent_tab(), "工作区 / Coding Agent")
        self.tabs.addTab(self._build_proactive_tab(), "主动行为")
        if initial_tab:
            for index in range(self.tabs.count()):
                if self.tabs.tabText(index) == initial_tab:
                    self.tabs.setCurrentIndex(index)
                    break
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存并立即应用")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

    def _build_personality_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.personality = QComboBox()
        for key, preset in PERSONALITY_PRESETS.items():
            self.personality.addItem(preset["name"], key)
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
        preset = PERSONALITY_PRESETS[key]
        description = f"{preset['core_identity']} {preset['tone']}"
        self.personality_help.setText(description or "使用下面填写的自定义性格。")
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

    def _build_proactive_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.proactive_enabled = QCheckBox("允许 Maidie 根据桌面状态主动提醒")
        self.proactive_enabled.setChecked(self.settings.get("proactive_enabled", False))
        self.proactive_tick = QSpinBox()
        self.proactive_tick.setRange(30, 60)
        self.proactive_tick.setSuffix(" 秒")
        self.proactive_tick.setValue(self.settings.get("proactive_tick_seconds", 45))
        self.proactive_cooldown = QSpinBox()
        self.proactive_cooldown.setRange(1, 240)
        self.proactive_cooldown.setSuffix(" 分钟")
        self.proactive_cooldown.setValue(max(1, self.settings.get("proactive_cooldown_seconds", 900) // 60))
        self.screen_awareness_enabled = QCheckBox("允许定时截屏并在本机进行 OCR")
        self.screen_awareness_enabled.setChecked(self.settings.get("screen_awareness_enabled", False))
        self.screen_awareness_interval = QSpinBox()
        self.screen_awareness_interval.setRange(30, 600)
        self.screen_awareness_interval.setSuffix(" 秒")
        self.screen_awareness_interval.setValue(self.settings.get("screen_awareness_interval", 60))
        note = QLabel("默认关闭。不会记录键盘内容；启用屏幕理解后，OCR 在本机完成，但相关文字可能随当前 Agent 任务发送给已配置的 AI 服务。节流期间不会重复打扰。")
        note.setWordWrap(True)
        layout.addRow("主动开关", self.proactive_enabled)
        layout.addRow("观察间隔", self.proactive_tick)
        layout.addRow("最短打扰间隔", self.proactive_cooldown)
        layout.addRow("屏幕理解", self.screen_awareness_enabled)
        layout.addRow("OCR 间隔", self.screen_awareness_interval)
        layout.addRow("", note)
        return page

    def _build_animation_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.animation_backend = QComboBox()
        self.animation_backend.addItem("Sprite（默认）", "sprite")
        self.animation_backend.addItem("Live2D Web（实验性）", "live2d_web")
        backend_index = self.animation_backend.findData(
            self.settings.get("animation_backend", "sprite")
        )
        self.animation_backend.setCurrentIndex(max(0, backend_index))

        self.live2d_model_root = QLineEdit(
            self.settings.get("animation_live2d_model_root", "")
        )
        self.live2d_model_root.setPlaceholderText("选择已解压的 Live2D 模型根目录")
        choose_button = QPushButton("选择目录")
        choose_button.clicked.connect(self._choose_live2d_root)
        scan_button = QPushButton("扫描模型")
        scan_button.setObjectName("scanLive2DModelsButton")
        scan_button.clicked.connect(self._scan_live2d_models)
        self.scan_live2d_button = scan_button
        root_row = QWidget()
        root_layout = QHBoxLayout(root_row)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.live2d_model_root, 1)
        root_layout.addWidget(choose_button)
        root_layout.addWidget(scan_button)

        self.live2d_model = QComboBox()
        self.live2d_model.currentIndexChanged.connect(self._update_live2d_preview)
        self._populate_live2d_models()
        apply_button = QPushButton("应用所选模型")
        apply_button.clicked.connect(self._apply_live2d_model)
        preview_button = QPushButton("预览模型")
        preview_button.setObjectName("previewLive2DModelButton")
        preview_button.clicked.connect(self._preview_live2d_model)
        browser_preview_button = QPushButton("用浏览器预览")
        browser_preview_button.setObjectName("browserPreviewLive2DModelButton")
        browser_preview_button.clicked.connect(self._preview_live2d_model_in_browser)
        sprite_button = QPushButton("回退 Sprite")
        sprite_button.clicked.connect(self._fallback_to_sprite)
        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.addWidget(apply_button)
        action_layout.addWidget(preview_button)
        action_layout.addWidget(browser_preview_button)
        action_layout.addWidget(sprite_button)

        self.live2d_preview_label = QLabel()
        self.live2d_preview_label.setObjectName("live2dPreviewStatus")
        self.live2d_preview_label.setWordWrap(True)
        note = QLabel(
            "预览在独立窗口中运行，不替换主桌宠渲染。"
            "缺少 PyQt6-WebEngine、Live2D Web Runtime 或模型失效时会明确报错。"
        )
        note.setWordWrap(True)
        layout.addRow("当前后端", self.animation_backend)
        layout.addRow("模型根目录", root_row)
        layout.addRow("已扫描模型", self.live2d_model)
        layout.addRow("操作", action_row)
        layout.addRow("预览 / 状态", self.live2d_preview_label)
        layout.addRow("", note)
        self._update_live2d_preview()
        return page

    def _choose_live2d_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "选择 Live2D 模型根目录", self.live2d_model_root.text().strip()
        )
        if selected:
            self.live2d_model_root.setText(selected)

    def _scan_live2d_models(self) -> None:
        root = self.live2d_model_root.text().strip()
        if not root:
            self.live2d_preview_label.setText("请先选择 Live2D 模型根目录。")
            return
        if self._live2d_scan_thread is not None:
            return
        self.scan_live2d_button.setEnabled(False)
        self.live2d_preview_label.setText("正在后台递归扫描 *.model3.json …")
        thread = QThread(self)
        worker = _Live2DScanWorker(root)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._finish_live2d_scan)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._live2d_scan_thread = thread
        self._live2d_scan_worker = worker
        thread.start()

    @pyqtSlot(object)
    def _finish_live2d_scan(self, result: object) -> None:
        payload = result if isinstance(result, dict) else {}
        self._live2d_scan_thread = None
        self._live2d_scan_worker = None
        self.scan_live2d_button.setEnabled(True)
        if not payload.get("ok"):
            self.live2d_preview_label.setText(
                f"扫描失败：{payload.get('error', '未知错误')}。将保持 Sprite。"
            )
            self._fallback_to_sprite()
            return
        current = self.live2d_model.currentData() or self.live2d_registry.current_model_id
        self.live2d_registry = AnimationModelRegistry(payload.get("models", []), current)
        count = len(self.live2d_registry.list_models())
        if not count:
            self._populate_live2d_models()
            self.live2d_preview_label.setText(
                "未扫描到 *.model3.json。ZIP 不会被自动解压，请先在仓库外解压模型。"
            )
            self._fallback_to_sprite()
        else:
            if self.live2d_registry.resolve_current_model() is None:
                self.live2d_registry.set_current_model(
                    self.live2d_registry.list_models()[0].id
                )
            self._populate_live2d_models()
            self._update_live2d_preview()
            self.live2d_preview_label.setText(
                f"已扫描到 {count} 个 Live2D 模型，已选择 "
                f"{self.live2d_model.currentText()}。"
            )

    def _populate_live2d_models(self) -> None:
        if not hasattr(self, "live2d_model"):
            return
        current = self.live2d_registry.current_model_id
        self.live2d_model.blockSignals(True)
        self.live2d_model.clear()
        self.live2d_model.addItem("未选择", "")
        for model in self.live2d_registry.list_models():
            self.live2d_model.addItem(model.name, model.id)
        index = self.live2d_model.findData(current)
        self.live2d_model.setCurrentIndex(max(0, index))
        self.live2d_model.blockSignals(False)

    def _update_live2d_preview(self) -> None:
        if not hasattr(self, "live2d_preview_label"):
            return
        model_id = self.live2d_model.currentData() if hasattr(self, "live2d_model") else ""
        model = next((item for item in self.live2d_registry.list_models()
                      if item.id == model_id), None)
        status = self.live2d_preview.inspect(model)
        details = f"\n{status.model_name}\n{status.model3_json}" if status.model3_json else ""
        self.live2d_preview_label.setText(status.message + details)

    def _apply_live2d_model(self) -> None:
        model_id = str(self.live2d_model.currentData() or "")
        try:
            model = self.live2d_registry.set_current_model(model_id)
        except (KeyError, FileNotFoundError) as exc:
            self.live2d_preview_label.setText(f"{exc}。将保持 Sprite。")
            self._fallback_to_sprite()
            return
        status = self.live2d_preview.inspect(model)
        if not status.available:
            self.animation_backend.setCurrentIndex(
                self.animation_backend.findData("sprite")
            )
            self.live2d_preview_label.setText(status.message + f"\n{model.name}\n{model.model3_json}")
            return
        self.animation_backend.setCurrentIndex(
            self.animation_backend.findData("live2d_web")
        )
        self.live2d_preview_label.setText(status.message + f"\n{model.name}\n{model.model3_json}")

    def _preview_live2d_model(self) -> None:
        model_id = str(self.live2d_model.currentData() or "")
        model = next((item for item in self.live2d_registry.list_models()
                      if item.id == model_id), None)
        dialog, result = create_live2d_preview_dialog(model, self)
        message = str(result.get("message", "预览不可用。"))
        if result.get("code") == "webengine_missing":
            message += " 可使用浏览器预览继续验证 Live2D 模型。"
        self.live2d_preview_label.setText(message)
        if dialog is None:
            return
        self._live2d_preview_windows.append(dialog)
        dialog.status_changed.connect(self._show_live2d_process_status)
        dialog.finished.connect(
            lambda _value, window=dialog: self._forget_live2d_preview(window)
        )
        dialog.show()

    def _show_live2d_process_status(self, payload: object) -> None:
        result = payload if isinstance(payload, dict) else {}
        self.live2d_preview_label.setText(str(result.get("message", "预览不可用。")))

    def _preview_live2d_model_in_browser(self) -> None:
        model_id = str(self.live2d_model.currentData() or "")
        model = next((item for item in self.live2d_registry.list_models()
                      if item.id == model_id), None)
        if model is None:
            self.live2d_preview_label.setText("未选择有效的 Live2D 模型。")
            return
        server, result = open_browser_preview(model)
        self.live2d_preview_label.setText(str(result.get("message", "浏览器预览不可用。")))
        if server is not None:
            self._live2d_preview_servers.append(server)

    def _forget_live2d_preview(self, dialog: QDialog) -> None:
        if dialog in self._live2d_preview_windows:
            self._live2d_preview_windows.remove(dialog)

    def _fallback_to_sprite(self) -> None:
        if hasattr(self, "animation_backend"):
            self.animation_backend.setCurrentIndex(self.animation_backend.findData("sprite"))
        if hasattr(self, "live2d_preview_label"):
            self.live2d_preview_label.setText("已选择 Sprite 后端。")

    def _build_coding_agent_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.workspace_root = QLineEdit(self.settings.get("workspace_root", ""))
        self.workspace_root.setPlaceholderText("选择允许 Coding Agent 读取的项目目录")
        choose_button = QPushButton("选择项目目录")
        choose_button.setObjectName("chooseWorkspaceButton")
        choose_button.clicked.connect(self._choose_workspace)
        workspace_row = QWidget()
        workspace_layout = QHBoxLayout(workspace_row)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.addWidget(self.workspace_root, 1)
        workspace_layout.addWidget(choose_button)

        self.coding_agent_enabled = QCheckBox("启用本机只读 Coding Agent")
        self.coding_agent_enabled.setChecked(
            self.settings.get("coding_agent_enabled", False)
        )
        self.coding_agent_provider = QComboBox()
        self.coding_agent_provider.addItem("OpenCode", "opencode")
        self.coding_agent_provider.addItem("Codex", "codex")
        provider_index = self.coding_agent_provider.findData(
            self.settings.get("coding_agent_provider", "opencode")
        )
        self.coding_agent_provider.setCurrentIndex(max(0, provider_index))
        self.coding_agent_command = QLineEdit(
            self.settings.get("coding_agent_command", "opencode")
        )
        self.coding_agent_command.setPlaceholderText("例如 opencode、codex 或可执行文件完整路径")
        self.coding_agent_timeout = QSpinBox()
        self.coding_agent_timeout.setRange(1, 600)
        self.coding_agent_timeout.setSuffix(" 秒")
        self.coding_agent_timeout.setValue(
            self.settings.get("coding_agent_timeout_seconds", 120)
        )
        self.coding_agent_dry_run = QCheckBox("强制只读分析（dry-run）")
        self.coding_agent_dry_run.setChecked(True)
        self.coding_agent_dry_run.setEnabled(False)
        test_button = QPushButton("测试 Coding Agent")
        test_button.setObjectName("testCodingAgentButton")
        test_button.clicked.connect(self._test_coding_agent)
        self.coding_agent_test_result = QLabel("尚未测试")
        self.coding_agent_test_result.setObjectName("codingAgentTestResult")
        self.coding_agent_test_result.setWordWrap(True)
        self.install_method = QComboBox()
        self.install_method.setObjectName("openCodeInstallMethod")
        self.detect_opencode_button = QPushButton("检测 OpenCode")
        self.detect_opencode_button.clicked.connect(self._detect_opencode)
        self.install_opencode_button = QPushButton("安装 OpenCode")
        self.install_opencode_button.clicked.connect(self._install_opencode)
        self.redetect_opencode_button = QPushButton("重新检测")
        self.redetect_opencode_button.clicked.connect(self._detect_opencode)
        install_buttons = QWidget()
        install_buttons_layout = QHBoxLayout(install_buttons)
        install_buttons_layout.setContentsMargins(0, 0, 0, 0)
        install_buttons_layout.addWidget(self.detect_opencode_button)
        install_buttons_layout.addWidget(self.install_opencode_button)
        install_buttons_layout.addWidget(self.redetect_opencode_button)
        self.install_log = QTextEdit()
        self.install_log.setObjectName("openCodeInstallLog")
        self.install_log.setReadOnly(True)
        self.install_log.setPlaceholderText("检测和安装结果会显示在这里。")
        self.install_log.setMaximumHeight(120)
        self.opencode_setup_status = QLabel()
        self.opencode_setup_status.setWordWrap(True)
        open_config = QPushButton("打开 OpenCode 配置")
        open_config.clicked.connect(lambda: self._open_opencode_terminal("connect"))
        open_init = QPushButton("打开 OpenCode 初始化")
        open_init.clicked.connect(lambda: self._open_opencode_terminal("init"))
        readonly_test = QPushButton("只读联调测试")
        readonly_test.clicked.connect(self._run_readonly_coding_test)
        setup_buttons = QWidget(); setup_layout = QHBoxLayout(setup_buttons)
        setup_layout.setContentsMargins(0, 0, 0, 0)
        setup_layout.addWidget(open_config); setup_layout.addWidget(open_init); setup_layout.addWidget(readonly_test)
        note = QLabel(
            "测试只检查目录、provider 和命令是否可用，不会启动 Agent。第一版始终禁止写文件、"
            "shell、依赖安装、commit 和 push。"
        )
        note.setWordWrap(True)
        layout.addRow("项目工作区", workspace_row)
        layout.addRow("启用", self.coding_agent_enabled)
        layout.addRow("Provider", self.coding_agent_provider)
        layout.addRow("Command", self.coding_agent_command)
        layout.addRow("超时", self.coding_agent_timeout)
        layout.addRow("运行模式", self.coding_agent_dry_run)
        layout.addRow("", test_button)
        layout.addRow("测试结果", self.coding_agent_test_result)
        layout.addRow("安装方式", self.install_method)
        layout.addRow("OpenCode", install_buttons)
        layout.addRow("安装日志", self.install_log)
        layout.addRow("初始化状态", self.opencode_setup_status)
        layout.addRow("", setup_buttons)
        layout.addRow("", note)
        self._refresh_install_methods(write_log=False)
        self._refresh_setup_status()
        return page

    def _choose_workspace(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "选择项目目录", self.workspace_root.text().strip()
        )
        if selected:
            self.workspace_root.setText(selected)
            self.coding_agent_test_result.setText("尚未测试")

    def _test_coding_agent(self) -> None:
        result = CodingAgentTool.validate_configuration(
            self.workspace_root.text(),
            str(self.coding_agent_provider.currentData() or ""),
            self.coding_agent_command.text(),
            self.coding_agent_dry_run.isChecked(),
        )
        self.coding_agent_test_result.setText(str(result["message"]))
        color = "#317a45" if result["ok"] else "#a33d52"
        self.coding_agent_test_result.setStyleSheet(f"color: {color}; font-weight: 600;")

    def _refresh_install_methods(self, write_log: bool = True) -> dict[str, str]:
        methods = self.coding_agent_installer.detect_install_methods()
        previous = self.install_method.currentData()
        self.install_method.clear()
        labels = {"npm": "npm（推荐）", "scoop": "Scoop", "choco": "Chocolatey"}
        for method, executable in methods.items():
            self.install_method.addItem(labels[method], method)
            self.install_method.setItemData(self.install_method.count() - 1, executable,
                                            Qt.ItemDataRole.ToolTipRole)
        previous_index = self.install_method.findData(previous)
        self.install_method.setCurrentIndex(max(0, previous_index))
        self.install_opencode_button.setEnabled(bool(methods) and self._install_thread is None)
        if write_log:
            if methods:
                names = "、".join(labels[name] for name in methods)
                self.install_log.append(f"检测到安装方式：{names}")
            else:
                self.install_log.append("未检测到 npm、Scoop 或 Chocolatey。")
                self.install_log.append("请先安装 Node.js、Scoop 或 Chocolatey 后重试。")
                self.install_log.append("Maidie 不会自动安装这些前置环境。")
        return methods

    def _detect_opencode(self) -> None:
        executable = self.coding_agent_installer.detect_opencode()
        if executable:
            self.install_log.append(f"OpenCode 可用：{executable}")
            self.coding_agent_test_result.setText("可用")
        else:
            self.install_log.append("未检测到 OpenCode。")
        self._refresh_install_methods()
        self._refresh_setup_status()

    def _refresh_setup_status(self) -> dict:
        status = self.coding_agent_installer.detect_setup_status(self.workspace_root.text())
        parts = ["OpenCode：" + ("已安装" if status["installed"] else "未安装"),
                 "模型配置：" + ("疑似已配置" if status["provider_config_detected"] else "未检测到配置，建议执行 /connect"),
                 "AGENTS.md：" + ("项目上下文已初始化" if status["agents_md"] else "未检测到，建议执行 /init")]
        self.opencode_setup_status.setText("\n".join(parts))
        return status

    def _open_opencode_terminal(self, mode: str) -> None:
        instruction = "/connect 配置模型 provider / API Key" if mode == "connect" else "/init 生成 AGENTS.md"
        QMessageBox.information(self, "OpenCode 可见终端", f"终端打开后，请在 OpenCode 中执行 {instruction}。\nMaidie 不会读取或保存 API Key。")
        result = self.coding_agent_installer.open_visible_terminal(self.workspace_root.text())
        if not result.get("ok"):
            self.install_log.append(str(result.get("error") or "无法打开 OpenCode"))

    def _run_readonly_coding_test(self) -> None:
        if not self.workspace_root.text().strip():
            self.install_log.append("只读联调失败：workspace 未配置")
            return
        if not self.coding_agent_enabled.isChecked():
            self.install_log.append("只读联调失败：Coding Agent 未启用")
            return
        self.coding_agent_dry_run.setChecked(True)
        self.controller.submit_text("用 OpenCode 对当前项目执行只读 test plan，不修改文件，不执行 shell，不提交代码")

    def _install_opencode(self) -> None:
        methods = self._refresh_install_methods(write_log=False)
        method = str(self.install_method.currentData() or "")
        if not methods or method not in methods:
            self._refresh_install_methods(write_log=True)
            return
        message = (
            "将安装第三方 CLI 工具 OpenCode。\n\n"
            "• 将从网络下载内容\n"
            "• 安装过程可能需要一段时间\n"
            "• OpenCode 仍需要你自行配置模型 API Key\n"
            "• Maidie 不会修改项目文件\n\n"
            f"安装方式：{method}"
        )
        answer = QMessageBox.question(
            self, "确认安装 OpenCode", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.install_log.append("用户已取消安装，未执行任何命令。")
            return
        self.install_log.append(f"开始通过 {method} 安装 OpenCode……")
        self._set_install_controls_enabled(False)
        thread = QThread(self)
        worker = _OpenCodeInstallWorker(self.coding_agent_installer, method)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_install_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._clear_install_thread)
        self._install_thread = thread
        self._install_worker = worker
        thread.start()

    def _on_install_finished(self, result: dict) -> None:
        stdout = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        if stdout:
            self.install_log.append(stdout)
        if stderr:
            self.install_log.append(stderr)
        if result.get("success"):
            self.install_log.append("OpenCode 安装成功，重新检测已通过。")
            provider_index = self.coding_agent_provider.findData("opencode")
            self.coding_agent_provider.setCurrentIndex(max(0, provider_index))
            self.coding_agent_command.setText("opencode")
            self.coding_agent_dry_run.setChecked(True)
            self.coding_agent_test_result.setText("可用")
        else:
            self.install_log.append(f"OpenCode 安装失败：{result.get('error') or '未知错误'}")

    def _clear_install_thread(self) -> None:
        self._install_thread = None
        self._install_worker = None
        self._set_install_controls_enabled(True)
        self._refresh_install_methods(write_log=False)

    def _set_install_controls_enabled(self, enabled: bool) -> None:
        self.detect_opencode_button.setEnabled(enabled)
        self.redetect_opencode_button.setEnabled(enabled)
        self.install_method.setEnabled(enabled)
        self.install_opencode_button.setEnabled(enabled)

    def _build_vision_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.vision_workspace_id = QLineEdit(
            self.settings.get("vision_workspace_id", "")
        )
        self.vision_workspace_id.setPlaceholderText("阿里云百炼 Workspace ID")
        self.vision_api_key = QLineEdit()
        self.vision_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.vision_api_key.setPlaceholderText(
            "已配置；留空保持不变"
            if self.settings.get("has_vision_api_key") else "输入 DASHSCOPE API Key"
        )
        self.vision_model = QLineEdit(
            self.settings.get("vision_model", "qwen3-vl-flash")
        )
        self.vision_region = QComboBox()
        self.vision_region.addItem("北京（cn-beijing）", "cn-beijing")
        region_index = self.vision_region.findData(
            self.settings.get("vision_region", "cn-beijing")
        )
        self.vision_region.setCurrentIndex(max(0, region_index))
        self.vision_max_width = QSpinBox()
        self.vision_max_width.setRange(320, 4096)
        self.vision_max_width.setSuffix(" px")
        self.vision_max_width.setValue(self.settings.get("vision_max_width", 1280))
        self.vision_jpeg_quality = QSpinBox()
        self.vision_jpeg_quality.setRange(40, 100)
        self.vision_jpeg_quality.setValue(
            self.settings.get("vision_jpeg_quality", 85)
        )
        self.vision_cache_ttl = QSpinBox()
        self.vision_cache_ttl.setRange(0, 60)
        self.vision_cache_ttl.setSuffix(" 秒")
        self.vision_cache_ttl.setValue(
            self.settings.get("vision_cache_ttl_seconds", 5)
        )
        self.vision_default_scope = QComboBox()
        self.vision_default_scope.addItem("当前窗口", "active_window")
        self.vision_default_scope.addItem("全屏", "fullscreen")
        self.vision_default_scope.addItem("鼠标附近", "cursor_region")
        scope_index = self.vision_default_scope.findData(
            self.settings.get("vision_default_scope", "active_window")
        )
        self.vision_default_scope.setCurrentIndex(max(0, scope_index))
        self.vision_cursor_width = QSpinBox()
        self.vision_cursor_width.setRange(200, 4096)
        self.vision_cursor_width.setSuffix(" px")
        self.vision_cursor_width.setValue(
            self.settings.get("vision_cursor_region_width", 1000)
        )
        self.vision_cursor_height = QSpinBox()
        self.vision_cursor_height.setRange(200, 2160)
        self.vision_cursor_height.setSuffix(" px")
        self.vision_cursor_height.setValue(
            self.settings.get("vision_cursor_region_height", 800)
        )
        note = QLabel(
            "只有你明确要求看屏幕、窗口或图片时才会截图并发送给千问视觉；"
            "截图仅在内存中处理，不会永久保存。环境变量配置优先于这里的设置。"
        )
        note.setWordWrap(True)
        layout.addRow("Workspace ID", self.vision_workspace_id)
        layout.addRow("API Key", self.vision_api_key)
        layout.addRow("视觉模型", self.vision_model)
        layout.addRow("地域", self.vision_region)
        layout.addRow("图片最大宽度", self.vision_max_width)
        layout.addRow("JPEG 质量", self.vision_jpeg_quality)
        layout.addRow("短缓存", self.vision_cache_ttl)
        layout.addRow("默认截图范围", self.vision_default_scope)
        layout.addRow("鼠标区域宽度", self.vision_cursor_width)
        layout.addRow("鼠标区域高度", self.vision_cursor_height)
        scope_note = QLabel(
            "建议使用当前窗口。全屏信息更完整但隐私更多；鼠标附近适合按钮和局部内容。"
        )
        scope_note.setWordWrap(True)
        layout.addRow("", scope_note)
        layout.addRow("", note)
        return page

    def _save(self) -> None:
        if self._install_thread is not None:
            QMessageBox.information(self, "OpenCode 正在安装", "请等待安装完成后再保存设置。")
            return
        if self.animation_backend.currentData() == "live2d_web":
            model = self.live2d_registry.resolve_current_model()
            status = self.live2d_preview.inspect(model)
            if not status.available:
                self.animation_backend.setCurrentIndex(self.animation_backend.findData("sprite"))
                self.live2d_preview_label.setText(status.message)
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
            "proactive_enabled": self.proactive_enabled.isChecked(),
            "proactive_tick_seconds": self.proactive_tick.value(),
            "proactive_cooldown_seconds": self.proactive_cooldown.value() * 60,
            "screen_awareness_enabled": self.screen_awareness_enabled.isChecked(),
            "screen_awareness_interval": self.screen_awareness_interval.value(),
            "vision_workspace_id": self.vision_workspace_id.text().strip(),
            "vision_api_key": self.vision_api_key.text().strip(),
            "vision_model": self.vision_model.text().strip(),
            "vision_region": self.vision_region.currentData(),
            "vision_max_width": self.vision_max_width.value(),
            "vision_jpeg_quality": self.vision_jpeg_quality.value(),
            "vision_cache_ttl_seconds": self.vision_cache_ttl.value(),
            "vision_default_scope": self.vision_default_scope.currentData(),
            "vision_cursor_region_width": self.vision_cursor_width.value(),
            "vision_cursor_region_height": self.vision_cursor_height.value(),
            "workspace_root": self.workspace_root.text().strip(),
            "coding_agent_enabled": self.coding_agent_enabled.isChecked(),
            "coding_agent_provider": self.coding_agent_provider.currentData(),
            "coding_agent_command": self.coding_agent_command.text().strip(),
            "coding_agent_timeout_seconds": self.coding_agent_timeout.value(),
            "coding_agent_dry_run": True,
            "animation_backend": self.animation_backend.currentData(),
            "animation_current_model_id": str(self.live2d_model.currentData() or ""),
            "animation_live2d_model_root": self.live2d_model_root.text().strip(),
            "animation_live2d_models": [
                model.to_dict() for model in self.live2d_registry.list_models()
            ],
        }
        if not values["base_url"] or not values["chat_model"] or not values["technical_model"]:
            return
        self.controller.apply_settings(values)
        self.accept()

    def reject(self) -> None:
        if self._live2d_scan_thread is not None:
            QMessageBox.information(self, "正在扫描", "请等待 Live2D 模型扫描完成。")
            return
        if self._install_thread is not None:
            QMessageBox.information(self, "OpenCode 正在安装", "请等待安装完成后再关闭设置。")
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._live2d_scan_thread is not None:
            event.ignore()
            return
        if self._install_thread is not None:
            event.ignore()
            return
        super().closeEvent(event)
