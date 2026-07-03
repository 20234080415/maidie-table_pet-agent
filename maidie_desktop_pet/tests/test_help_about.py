from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel

from core.version import APP_AUTHOR, APP_DESCRIPTION, APP_NAME, APP_VERSION
from ui.dialogs import SettingsDialog
from ui.settings import AboutPage, HelpPage


class _Controller:
    def settings_snapshot(self):
        return {}

    def apply_settings(self, _values):
        pass


class VersionInformationTests(unittest.TestCase):
    def test_application_identity_is_available(self):
        self.assertEqual(APP_NAME, "Maidie Desktop Pet")
        self.assertEqual(APP_VERSION, "0.1.0-dev")
        self.assertEqual(APP_AUTHOR, "tyz")
        self.assertTrue(APP_DESCRIPTION)


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
        self.assertEqual(version.text(), f"版本：v{APP_VERSION}")
        self.assertEqual(name.text(), APP_NAME)
        page.close()

    def test_settings_dialog_exposes_help_and_about_tabs(self):
        dialog = SettingsDialog(_Controller())
        labels = [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())]
        self.assertIn("帮助与说明", labels)
        self.assertIn("关于 Maidie", labels)
        self.assertIn("模型与 API", labels)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
