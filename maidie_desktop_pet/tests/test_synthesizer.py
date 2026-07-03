from __future__ import annotations

import unittest

from core.brain.synthesizer import Synthesizer


class OfflineClient:
    api_key = ""


class SynthesizerTimeDeltaTests(unittest.TestCase):
    def test_structured_delta_response_uses_all_facts(self):
        synthesizer = Synthesizer(OfflineClient())
        data = {"type": "time_delta", "now": "16:27",
                "target": "17:40", "remaining_text": "1小时13分钟", "event": "下课",
                "status": "upcoming", "source": "local"}
        result = synthesizer.synthesize("还有多久下课", "tool", None,
                                        [{"tool": "time", "ok": True, "data": data}], "", [])
        for expected in ["16:27", "17:40", "1小时13分钟"]:
            self.assertIn(expected, result["text"])
        for forbidden in ["看不到时钟", "看不到屏幕", "让我看看屏幕", "你得告诉我下课时间"]:
            self.assertNotIn(forbidden, result["text"])


if __name__ == "__main__": unittest.main()
