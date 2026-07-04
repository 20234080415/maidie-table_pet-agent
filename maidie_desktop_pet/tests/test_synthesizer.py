from __future__ import annotations

import unittest

from core.brain.synthesizer import Synthesizer


class OfflineClient:
    api_key = ""


class PersonaClient:
    api_key = "configured"

    def ask(self, prompt, _context):
        self.prompt = prompt
        return {"text": "已经检查完了，详细重点在旁边的卡片里。",
                "emotion": "idle", "action": "talk", "state": "talking"}


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
        self.assertEqual(result["display_type"], "coding_analysis")
        self.assertIn("项目分析完成", result["content"]["project_overview"])
        self.assertEqual(result["content"]["key_findings"], ["入口过重"])
        self.assertEqual(result["content"]["priority_suggestions"], ["拆分协调逻辑"])
        self.assertEqual(result["content"]["validation_suggestions"], ["增加路由测试"])

    def test_coding_agent_reply_is_concise_and_has_no_raw_json(self):
        synthesizer = Synthesizer(OfflineClient())
        data = {"type": "coding_agent", "source": "local_opencode", "raw": {
            "summary": "分析完成", "findings": ["一", "二", "三", "不应展示"],
            "suggested_changes": ["建议一", "建议二", "建议三"],
            "tests_suggested": ["验证一", "验证二"],
        }}
        result = synthesizer.synthesize(
            "分析项目", "code_task", None,
            [{"tool": "coding_agent", "ok": True, "data": data}], "", [],
        )
        self.assertLess(len(result["text"]), len(result["panel_text"]))
        self.assertIn("优先问题", result["panel_text"])
        self.assertIn("优先建议", result["panel_text"])
        self.assertNotIn("{'project_name'", result["panel_text"])
        self.assertNotIn("```json", result["panel_text"])

    def test_coding_short_text_is_generated_by_persona_aware_synthesizer(self):
        client = PersonaClient()
        synthesizer = Synthesizer(client, personality_prompt="保持当前用户选择的表达方式")
        data = {"type": "coding_agent", "raw": {
            "project_name": "Demo", "findings": ["入口模块职责过多"],
        }}
        result = synthesizer.synthesize(
            "分析项目", "code_task", None,
            [{"tool": "coding_agent", "ok": True, "data": data}], "", [],
        )
        self.assertIn("详细重点在旁边的卡片里", result["text"])
        self.assertIn("保持当前用户选择的表达方式", client.prompt)

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
