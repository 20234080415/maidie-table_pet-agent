from __future__ import annotations

import unittest

from ui.window import format_system_confirmation


class FileConfirmationUiTests(unittest.TestCase):
    def test_file_plan_preview_contains_required_fields(self) -> None:
        message = format_system_confirmation("copy_file", {"file_plan": {
            "operation": "copy_file",
            "workspace": "Documents",
            "source": r"C:\Users\demo\Documents\a.txt",
            "destination": r"C:\Users\demo\Documents\b.txt",
            "destination_exists": True,
            "overwrite": True,
            "risk": "high",
            "risk_reasons": ["overwrite_existing_file"],
            "estimated_items": 1,
        }})

        for expected in (
            "copy_file", "Documents", "a.txt", "b.txt", "目标已存在：是",
            "覆盖：是", "high", "overwrite_existing_file", "预计影响数量：1",
        ):
            self.assertIn(expected, message)

    def test_generic_confirmation_does_not_show_content(self) -> None:
        message = format_system_confirmation("copy_clipboard", {
            "text": "secret", "label": "safe",
        })
        self.assertNotIn("secret", message)
        self.assertIn("safe", message)

    def test_modify_and_delete_preview_shows_diff_scope_and_recycle_details(self) -> None:
        message = format_system_confirmation("delete_file", {"file_plan": {
            "operation": "delete_file", "workspace": "Primary",
            "source": r"C:\project\old.txt", "risk": "high",
            "risk_reasons": ["delete_file"], "estimated_items": 1,
            "impact_scope": "single_file", "recycle_bin": True,
            "file_details": {"size": 42, "created_time": 123.0},
            "diff": "--- old\n+++ new\n-old\n+new", "confirmation_stage": 2,
        }})

        for expected in (
            "single_file", "42 字节", "进入回收站：是", "第二次确认",
            "变更预览", "-old", "+new",
        ):
            self.assertIn(expected, message)


if __name__ == "__main__":
    unittest.main()
