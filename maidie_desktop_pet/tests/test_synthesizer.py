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

    def test_structured_coding_agent_facts_are_presented_locally(self):
        synthesizer = Synthesizer(OfflineClient())
        data = {"type": "coding_agent", "source": "local_opencode", "raw": {
            "summary": "项目分析完成", "findings": ["入口过重"],
            "suggested_changes": ["拆分协调逻辑"], "patch_preview": "",
            "tests_suggested": ["增加路由测试"],
        }}
        result = synthesizer.synthesize(
            "分析我的项目", "code_task", None,
            [{"tool": "coding_agent", "ok": True, "data": data}], "", [],
        )
        for expected in ["项目分析完成", "入口过重", "拆分协调逻辑", "增加路由测试"]:
            self.assertIn(expected, result["text"])

    def test_coding_agent_process_failures_have_actionable_messages(self):
        synthesizer = Synthesizer(OfflineClient())
        cases = {"timeout": "终止进程树", "idle_timeout": "/connect",
                 "needs_setup": "provider / API Key", "cancelled": "已经取消"}
        for code, expected in cases.items():
            data = {"type": "coding_agent", "source": "local_opencode",
                    "raw": {"error": code, "error_code": code}}
            result = synthesizer.synthesize("分析项目", "code_task", None,
                [{"tool": "coding_agent", "ok": False, "data": data}], "", [])
            self.assertIn(expected, result["text"])


if __name__ == "__main__": unittest.main()
