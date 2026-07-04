from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.long_response_panel import LongResponsePanel
from core.pet import PetController
from ui.window import PetWindow


class _Memory:
    def get_recent(self): return []
    def prompt_context(self): return ""
    def save(self, *_args): pass


class LongResponsePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_short_chat_stays_in_bubble(self):
        self.assertFalse(LongResponsePanel.should_show({
            "display_type": "short_chat", "text": "今天天气不错。",
        }))

    def test_long_text_and_coding_analysis_use_panel(self):
        self.assertTrue(LongResponsePanel.should_show({"text": "长" * 180}))
        self.assertTrue(LongResponsePanel.should_show({
            "display_type": "coding_analysis", "text": "分析完成。",
        }))

    def test_panel_renders_copies_and_closes_full_content(self):
        panel = LongResponsePanel()
        content = {
            "project_overview": "这是一个 C 项目。",
            "key_findings": ["文件打开模式错误"],
            "priority_suggestions": ["改用 O_RDWR"],
            "validation_suggestions": ["编译并运行测试"],
        }
        panel.show_result("项目分析结果", content)
        self.app.processEvents()
        shown = panel.browser.toPlainText()
        for expected in ("项目概览", "优先问题", "优先建议", "验证建议"):
            self.assertIn(expected, shown)

        panel.copy_button.click()
        self.assertEqual(QApplication.clipboard().text(), shown)
        panel.close_button.click()
        self.app.processEvents()
        self.assertFalse(panel.isVisible())
        panel.close()

    def test_long_content_is_not_inserted_into_small_bubble(self):
        controller = PetController(Mock(), _Memory())
        assets = Path(__file__).resolve().parents[1] / "assets"
        window = PetWindow(controller, assets)
        window._start_stream({"source": "code_task"})
        window._append_stream("分析完成，详细内容在结果卡片中。")
        full_text = "项目概览\n" + "完整分析内容。" * 40

        window._show_reply({
            "text": "分析完成，详细内容在结果卡片中。",
            "display_type": "coding_analysis",
            "panel_title": "项目分析结果",
            "panel_text": full_text,
            "content": {},
        })
        self.app.processEvents()

        self.assertNotIn("完整分析内容", window.bubble.toPlainText())
        self.assertEqual(window.long_response_panel.browser.toPlainText(), full_text)
        window.shutdown()
        window.close()


if __name__ == "__main__":
    unittest.main()
