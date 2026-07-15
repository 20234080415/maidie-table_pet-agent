from __future__ import annotations

import unittest

from core.brain.executor import BrainExecutor
from core.brain.llm_router import LLMIntentRouter
from core.brain.planner import BrainPlanner
from core.tools import ToolRegistry
from core.tools.base import Tool


class _NoLlmClient:
    def route_intent(self, _prompt, _context):
        raise AssertionError("high-confidence file requests should use deterministic routing")


class _CaptureSystemTool(Tool):
    name = "system"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def match(self, _query):
        return True

    def run(self, _query):
        raise AssertionError("file operations must use structured execute")

    def execute(self, action, params):
        self.calls.append((action, params))
        return {"type": "system", "source": "local", "raw": {
            "ok": True, "operation": action, "path": params.get("source"),
            "result": {}, "error_code": None, "message": "",
        }}


class FileNaturalLanguageRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = LLMIntentRouter(_NoLlmClient())
        self.planner = BrainPlanner()

    def _plan(self, text: str) -> tuple[dict, dict]:
        route = self.router.route(text)
        plan = self.planner.plan_route(text, route)
        self.assertEqual(route["task_type"], "file")
        self.assertEqual(plan["steps"][0]["tool"], "system")
        return route, plan["steps"][0]

    def test_directory_listing_uses_list_directory(self) -> None:
        route, step = self._plan("查看桌面有哪些文件")

        self.assertEqual(route["entities"]["operation"], "list_directory")
        self.assertEqual(route["entities"]["path"], "桌面")
        self.assertEqual(step["action"], "list_directory")
        self.assertEqual(step["params"]["source"], "桌面")

    def test_named_text_file_uses_read_file_with_full_alias_path(self) -> None:
        route, step = self._plan("读取桌面的test.txt")

        self.assertEqual(route["entities"]["operation"], "read_file")
        self.assertEqual(route["entities"]["path"], "桌面/test.txt")
        self.assertEqual(step["action"], "read_file")
        self.assertEqual(step["params"]["source"], "桌面/test.txt")

    def test_named_docx_analysis_uses_read_file(self) -> None:
        route, step = self._plan("分析桌面的秘籍.docx")

        self.assertEqual(route["entities"]["operation"], "read_file")
        self.assertEqual(step["action"], "read_file")
        self.assertEqual(step["params"]["source"], "桌面/秘籍.docx")

    def test_find_extension_uses_search_files(self) -> None:
        route, step = self._plan("找一下桌面所有md文件")

        self.assertEqual(route["entities"]["operation"], "search_files")
        self.assertEqual(route["entities"]["path"], "桌面")
        self.assertEqual(step["action"], "search_files")
        self.assertEqual(step["params"]["source"], "桌面")
        self.assertEqual(step["params"]["pattern"], "*.md")

    def test_view_and_summarize_named_files_are_reads_not_directory_queries(self) -> None:
        cases = {
            "查看桌面上的test.txt总结一下": "桌面/test.txt",
            "查看桌面上的秘籍.md总结分析一下": "桌面/秘籍.md",
        }
        for text, expected_path in cases.items():
            with self.subTest(text=text):
                route, step = self._plan(text)
                self.assertEqual(route["entities"]["operation"], "read_file")
                self.assertEqual(step["action"], "read_file")
                self.assertEqual(step["params"]["source"], expected_path)

    def test_required_phrases_reach_system_tool_with_expected_operation(self) -> None:
        cases = [
            ("查看桌面有哪些文件", "list_directory", "桌面", "*"),
            ("读取桌面的test.txt", "read_file", "桌面/test.txt", "*"),
            ("分析桌面的秘籍.docx", "read_file", "桌面/秘籍.docx", "*"),
            ("找一下桌面所有md文件", "search_files", "桌面", "*.md"),
        ]
        for text, operation, source, pattern in cases:
            with self.subTest(text=text):
                route = self.router.route(text)
                plan = self.planner.plan_route(text, route)
                tool = _CaptureSystemTool()
                execution = BrainExecutor(ToolRegistry([tool])).execute(plan, text)[0]

                self.assertTrue(execution["ok"])
                self.assertEqual(tool.calls[0][0], operation)
                self.assertEqual(tool.calls[0][1]["source"], source)
                self.assertEqual(tool.calls[0][1]["pattern"], pattern)

    def test_named_file_follow_up_goals_are_preserved(self) -> None:
        cases = {
            "读取test.txt": "none",
            "读取test.txt总结一下": "summary",
            "分析test.txt": "analysis",
            "读取test.txt解释一下": "explain",
            "读取test.txt提取版本号": "extract",
            "读取test.txt审查一下": "review",
            "读取test.txt并搜索相关资料": "search_related",
        }
        for text, expected_goal in cases.items():
            with self.subTest(text=text):
                route, step = self._plan(text)
                self.assertEqual(route["entities"]["goal"], expected_goal)
                self.assertEqual(step["params"]["goal"], expected_goal)


if __name__ == "__main__":
    unittest.main()
