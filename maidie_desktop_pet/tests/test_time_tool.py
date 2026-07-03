from __future__ import annotations

import unittest
from datetime import datetime

from core.tools.time_tool import TimeTool


class TimeToolDeltaTests(unittest.TestCase):
    def setUp(self):
        self.tool = TimeTool(lambda: datetime(2026, 7, 3, 16, 27, 0))

    def delta(self, target):
        return self.tool.execute("delta_until", target_time_text=target)["raw"]

    def test_supported_future_formats(self):
        for target, canonical, minutes in [("17:40", "17:40", 73), ("5.40", "17:40", 73),
                                            ("5:40", "17:40", 73), ("下午5点40", "17:40", 73),
                                            ("5点40", "05:40", 0),
                                            ("晚上8点", "20:00", 213), ("23:30", "23:30", 423)]:
            raw = self.delta(target)
            if target == "5点40":
                self.assertEqual(raw["status"], "elapsed", target)
                continue
            self.assertEqual(raw["status"], "upcoming", target)
            self.assertEqual(raw["target"], canonical, target)
            self.assertEqual(raw["remaining_minutes"], minutes, target)

    def test_elapsed_time_is_explicit(self):
        raw = self.delta("15:00")
        self.assertEqual(raw["status"], "elapsed")
        self.assertEqual(raw["remaining_text"], "已过")
        self.assertEqual(raw["remaining_minutes"], 0)


if __name__ == "__main__": unittest.main()
