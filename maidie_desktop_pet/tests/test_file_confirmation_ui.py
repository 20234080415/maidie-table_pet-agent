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


if __name__ == "__main__":
    unittest.main()
