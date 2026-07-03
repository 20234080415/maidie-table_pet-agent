from __future__ import annotations

import unittest

from core.session.task_context import ShortTermTaskContext


class ShortTermTaskContextTests(unittest.TestCase):
    def test_event_time_followups(self):
        for fact, followup, event, target in [
            ("我5.40下课", "还有多久下课", "下课", "5.40"),
            ("我晚上8点开会", "还剩多久开会", "开会", "晚上8点"),
            ("我6:20要出门", "还有多久出门", "出门", "6:20"),
            ("我9点交报告", "还有多久交报告", "交报告", "9点"),
        ]:
            context = ShortTermTaskContext()
            context.observe(fact)
            route = context.resolve(followup)
            self.assertIsNotNone(route)
            self.assertEqual(route["task_type"], "time_delta")
            self.assertEqual(route["entities"], {"target_time_text": target, "event": event})


if __name__ == "__main__": unittest.main()
