from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from core.version import (
    APP_AUTHOR, APP_DESCRIPTION, APP_NAME, APP_TECH_STACK, APP_VERSION,
)
from ui.about_dialog import AboutDialog
from ui.dialogs import SettingsDialog
from ui.coding_agent_console import CodingAgentConsole
from ui.help_dialog import HelpDialog
from ui.settings import AboutPage, HelpPage


class _Controller:
    def settings_snapshot(self):
        return {}

    def apply_settings(self, _values):
        pass


class VersionInformationTests(unittest.TestCase):
    def test_application_identity_is_available(self):
        self.assertEqual(APP_NAME, "Maidie Desktop Pet")
        self.assertEqual(APP_VERSION, "v0.1.0-dev")
        self.assertEqual(APP_AUTHOR, "tyz")
        self.assertTrue(APP_DESCRIPTION)
        self.assertEqual(APP_TECH_STACK, "Python + PyQt6 + LLM Agent + vision_ai")


class HelpAndAboutPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_help_page_contains_required_sections(self):
        page = HelpPage()
        text = page.browser.toPlainText()
        for section in ("基础操作", "聊天能力", "Agent 工具能力", "隐私说明", "常见问题"):
            self.assertIn(section, text)
        page.close()

    def test_about_page_reads_shared_version(self):
        page = AboutPage()
        version = page.findChild(QLabel, "aboutVersion")
        name = page.findChild(QLabel, "aboutAppName")
        self.assertIsNotNone(version)
        self.assertIsNotNone(name)
        self.assertEqual(version.text(), f"当前版本：{APP_VERSION}")
        self.assertEqual(name.text(), APP_NAME)
        page.close()

    def test_help_and_about_are_independent_dialogs(self):
        help_dialog = HelpDialog()
        about_dialog = AboutDialog()
        self.assertEqual(help_dialog.windowTitle(), "帮助与说明")
        self.assertEqual(about_dialog.windowTitle(), "关于 Maidie")
        help_dialog.close()
        about_dialog.close()

    def test_settings_dialog_no_longer_contains_help_and_about_tabs(self):
        dialog = SettingsDialog(_Controller())
        labels = [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())]
        self.assertNotIn("帮助与说明", labels)
        self.assertNotIn("关于 Maidie", labels)
        self.assertIn("模型与 API", labels)
        self.assertIn("工作区 / Coding Agent", labels)
        dialog.close()

    def test_settings_dialog_is_not_always_on_top_and_can_minimize(self):
        dialog = SettingsDialog(_Controller())
        flags = dialog.windowFlags()
        self.assertFalse(flags & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(flags & Qt.WindowType.WindowMinimizeButtonHint)
        dialog.close()

    def test_coding_agent_settings_are_read_only_and_testable(self):
        dialog = SettingsDialog(_Controller())
        self.assertTrue(dialog.coding_agent_dry_run.isChecked())
        self.assertFalse(dialog.coding_agent_dry_run.isEnabled())
        dialog._test_coding_agent()
        self.assertEqual(dialog.coding_agent_test_result.text(), "workspace 未配置")
        with tempfile.TemporaryDirectory() as root:
            dialog.workspace_root.setText(root)
            dialog.coding_agent_command.setText("opencode")
            with patch("core.tools.coding_agent_tool.shutil.which", return_value="opencode"):
                dialog._test_coding_agent()
            self.assertEqual(dialog.coding_agent_test_result.text(), "可用")
        dialog.close()

    def test_workspace_picker_updates_the_field(self):
        dialog = SettingsDialog(_Controller())
        with patch("ui.dialogs.QFileDialog.getExistingDirectory", return_value="C:/project"):
            dialog._choose_workspace()
        self.assertEqual(dialog.workspace_root.text(), "C:/project")
        dialog.close()

    def test_cancelled_opencode_install_runs_nothing(self):
        dialog = SettingsDialog(_Controller())
        dialog.coding_agent_installer.detect_install_methods = lambda: {"npm": "npm.cmd"}
        dialog._refresh_install_methods(write_log=False)
        dialog.coding_agent_installer.install_opencode = Mock()
        with patch("ui.dialogs.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.No):
            dialog._install_opencode()
        dialog.coding_agent_installer.install_opencode.assert_not_called()
        self.assertIn("取消", dialog.install_log.toPlainText())
        dialog.close()

    def test_failed_install_keeps_command_and_success_keeps_dry_run(self):
        dialog = SettingsDialog(_Controller())
        dialog.coding_agent_command.setText("custom-opencode")
        dialog._on_install_finished({"success": False, "error": "network error"})
        self.assertEqual(dialog.coding_agent_command.text(), "custom-opencode")
        dialog._on_install_finished({"success": True, "command_path": "opencode"})
        self.assertEqual(dialog.coding_agent_command.text(), "opencode")
        self.assertTrue(dialog.coding_agent_dry_run.isChecked())
        self.assertFalse(dialog.coding_agent_enabled.isChecked())
        dialog.close()

    def test_coding_console_buffers_200_lines_and_cancel_callback(self):
        cancel = Mock(); console = CodingAgentConsole(cancel)
        console.handle_event({"event": "start", "status": "running"})
        for index in range(220):
            console.handle_event({"event": "output", "stream": "stdout", "line": str(index)})
        self.assertEqual(len(console.lines), 200)
        self.assertTrue(next(iter(console.lines)).endswith("20"))
        console.cancel_callback()
        cancel.assert_called_once_with()
        console.handle_event({"event": "finish", "status": "cancelled"})
        self.assertIn("已取消", console.status.text())
        console.close()


if __name__ == "__main__":
    unittest.main()
