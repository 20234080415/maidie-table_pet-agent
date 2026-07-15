from __future__ import annotations

import unittest

from core.brain import BrainRouter
from core.tools import ToolRegistry
from core.tools.base import Tool


class _Memory:
    def prompt_context(self):
        return ""


class _RecoveryClient:
    api_key = "configured"

    def __init__(self) -> None:
        self.recovery_calls: list[dict] = []
        self.synthesis_prompts: list[str] = []

    def route_intent(self, _prompt, _context):
        raise AssertionError("file requests should use deterministic routing")

    def decide_recovery(self, payload):
        self.recovery_calls.append(payload)
        options = payload.get("options", [])
        return {"next_action": options[0]["id"] if options else "finish",
                "reason": "select the safest available recovery"}

    def ask(self, prompt, _context):
        self.synthesis_prompts.append(prompt)
        return {"text": "摘要：这是一本进阶指南。\n关键内容：需要先完成主线任务。",
                "emotion": "thinking", "action": "talk", "state": "talking"}


class _RecoveringSystemTool(Tool):
    name = "system"

    def __init__(self, *, candidate=True, approve=False, always_fail=False) -> None:
        self.candidate = candidate
        self.always_fail = always_fail
        self.calls: list[tuple[str, dict]] = []
        self.confirmations: list[tuple[str, dict]] = []
        self.confirmation_callback = self._confirm
        self.approve = approve

    def _confirm(self, action, params):
        self.confirmations.append((action, params))
        return self.approve

    def match(self, _query):
        return True

    def run(self, _query):
        raise AssertionError("structured file requests must use execute")

    def execute(self, operation, params):
        self.calls.append((operation, dict(params)))
        source = str(params.get("source") or "")
        if operation == "read_file" and source.endswith("秘籍.docx") and not self.always_fail:
            content = "进阶指南要求先完成主线任务。"
            return {"type": "system", "source": "local", "raw": {
                "ok": True, "operation": operation, "path": source,
                "file_type": "docx", "content": content,
                "result": {"content": content, "file_type": "docx"},
                "error_code": None, "message": "",
            }}
        if operation == "search_files" and not self.always_fail:
            items = ([{"name": "秘籍.docx", "path": "C:/Users/demo/Desktop/秘籍.docx",
                       "type": "file"}] if self.candidate else [])
            return {"type": "system", "source": "local", "raw": {
                "ok": True, "operation": operation, "path": source,
                "resolved_path": "C:/Users/demo/Desktop", "items": items,
                "result_count": len(items), "result": {"items": items},
                "error_code": None, "message": "",
            }}
        return {"type": "system", "source": "local", "raw": {
            "ok": False, "operation": operation, "path": source,
            "result": None, "error_code": "path_not_found",
            "message": "path does not exist",
        }}


class _EndlessRecovery:
    def decide(self, user_input, plan, executions, iteration, context):
        return {
            "finished": False, "next_action": "search_files", "tool": "system",
            "operation": "search_files", "progress": "正在寻找相似文件...",
            "params": {"source": "桌面", "pattern": "秘籍.*", "limit": 50},
        }


class AgentRecoveryLoopTests(unittest.TestCase):
    def _router(self, tool, client=None, recovery_analyzer=None):
        client = client or _RecoveryClient()
        return BrainRouter(
            client, client, ToolRegistry([tool]), _Memory(),
            recovery_analyzer=recovery_analyzer,
        ), client

    def test_missing_file_finds_candidate_and_requires_confirmation(self) -> None:
        tool = _RecoveringSystemTool(candidate=True, approve=False)
        router, client = self._router(tool)

        result = router.route("查看桌面上的秘籍.md总结分析一下")

        self.assertEqual([call[0] for call in tool.calls], ["read_file", "search_files"])
        self.assertEqual(len(tool.confirmations), 1)
        self.assertIn("秘籍.md", result["text"])
        self.assertIn("秘籍.docx", result["text"])
        self.assertIn("是否", result["text"])
        self.assertGreaterEqual(len(client.recovery_calls), 2)

    def test_approved_recovery_continues_read_and_summary(self) -> None:
        tool = _RecoveringSystemTool(candidate=True, approve=True)
        router, client = self._router(tool)

        result = router.route("查看桌面上的秘籍.md总结一下")

        self.assertEqual([call[0] for call in tool.calls],
                         ["read_file", "search_files", "read_file"])
        self.assertEqual(len(tool.confirmations), 1)
        rendered = str(result.get("panel_text") or result["text"])
        self.assertIn("摘要", rendered)
        self.assertEqual(len(client.synthesis_prompts), 1)

    def test_missing_file_searches_then_reports_no_candidates(self) -> None:
        tool = _RecoveringSystemTool(candidate=False)
        router, _client = self._router(tool)

        result = router.route("分析桌面上的abc.txt")

        self.assertEqual([call[0] for call in tool.calls], ["read_file", "search_files"])
        self.assertIn("abc.txt", result["text"])
        self.assertIn("没有找到相似文件", result["text"])

    def test_recovery_stops_after_three_execution_rounds(self) -> None:
        tool = _RecoveringSystemTool(always_fail=True)
        router, _client = self._router(tool, recovery_analyzer=_EndlessRecovery())

        router.route("分析桌面上的秘籍.md")

        self.assertEqual(len(tool.calls), 3)

    def test_progress_events_hide_recovery_reasoning(self) -> None:
        tool = _RecoveringSystemTool(candidate=False)
        router, _client = self._router(tool)
        events = []

        router.route("分析桌面上的abc.txt", on_delta=events.append)

        contents = [str(item.get("content") if isinstance(item, dict) else item) for item in events]
        self.assertTrue(any("寻找相似文件" in content for content in contents))
        self.assertFalse(any("select the safest" in content for content in contents))


if __name__ == "__main__":
    unittest.main()
