from __future__ import annotations

import unittest

from core.brain import BrainRouter
from core.tools import ToolRegistry
from core.tools.base import Tool


class _Memory:
    def prompt_context(self):
        return ""


class _ReasoningClient:
    api_key = "configured"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def route_intent(self, _prompt, _context):
        raise AssertionError("these file requests should use deterministic routing")

    def ask(self, prompt, _context):
        self.prompts.append(prompt)
        if '"next_action": "summary"' in prompt:
            text = "摘要：文档介绍安装与配置。\n关键内容：\n1. 准备运行环境\n2. 完成基础设置"
        elif '"next_action": "analysis"' in prompt:
            text = "文件主题：进阶玩法。\n主要问题：步骤缺少前置条件。\n建议：补充适用版本和风险说明。"
        else:
            raise AssertionError("file reasoning requires a supported continuation")
        return {"text": text, "emotion": "thinking", "action": "talk", "state": "talking"}


class _FileSystemTool(Tool):
    name = "system"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def match(self, _query):
        return True

    def run(self, _query):
        raise AssertionError("structured file requests must use execute")

    def execute(self, operation, params):
        self.calls.append((operation, dict(params)))
        path = str(params.get("source") or "")
        if "不存在.txt" in path:
            return {"type": "system", "source": "local", "raw": {
                "ok": False, "operation": operation, "path": path,
                "result": None, "error_code": "path_not_found",
                "message": "path does not exist",
            }}
        if operation == "list_directory":
            return {"type": "system", "source": "local", "raw": {
                "ok": True, "operation": operation, "path": path,
                "resolved_path": "C:/Users/demo/Desktop", "result_count": 1,
                "items": [{"name": "test.txt", "path": "C:/Users/demo/Desktop/test.txt",
                           "type": "file"}], "error_code": None, "message": "",
            }}
        content = (
            "第一章介绍安装流程。第二章记录基础配置和注意事项。"
            if path.endswith("test.txt") else
            "进阶玩法需要先完成主线。操作步骤没有标注适用版本。"
        )
        file_type = "docx" if path.endswith(".docx") else "text"
        return {"type": "system", "source": "local", "raw": {
            "ok": True, "operation": operation, "path": path,
            "file_type": file_type, "content": content,
            "result": {"content": content, "file_type": file_type},
            "error_code": None, "message": "",
        }}


class FileTaskContinuationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _ReasoningClient()
        self.system = _FileSystemTool()
        self.router = BrainRouter(
            self.client, self.client, ToolRegistry([self.system]), _Memory(),
        )

    def test_plain_read_returns_file_content_without_reasoning(self) -> None:
        result = self.router.route("读取test.txt")

        self.assertEqual(self.system.calls[0][0], "read_file")
        self.assertIn("第一章介绍安装流程", result["text"])
        self.assertEqual(self.client.prompts, [])

    def test_read_and_summarize_continues_into_reasoning(self) -> None:
        result = self.router.route("读取test.txt总结一下")

        self.assertEqual(self.system.calls[0][0], "read_file")
        full_text = str(result.get("panel_text") or result["text"])
        self.assertIn("摘要", full_text)
        self.assertIn("关键内容", full_text)
        self.assertNotIn("第二章记录基础配置和注意事项", full_text)
        self.assertEqual(len(self.client.prompts), 1)

    def test_docx_content_continues_into_analysis(self) -> None:
        result = self.router.route("分析秘籍.docx")

        self.assertEqual(self.system.calls[0][0], "read_file")
        self.assertIn("文件主题", result["text"])
        self.assertIn("主要问题", result["text"])
        self.assertIn("建议", result["text"])
        self.assertIn('"file_type": "docx"', self.client.prompts[0])

    def test_directory_listing_does_not_trigger_file_reasoning(self) -> None:
        result = self.router.route("查看桌面有哪些文件")

        self.assertEqual(self.system.calls[0][0], "list_directory")
        self.assertIn("test.txt", result["text"])
        self.assertEqual(self.client.prompts, [])

    def test_failed_read_does_not_continue_with_empty_content(self) -> None:
        result = self.router.route("分析不存在.txt")

        self.assertEqual(self.system.calls[0][0], "read_file")
        self.assertIn("没有成功", result["text"])
        self.assertIn("path_not_found", result["text"])
        self.assertEqual(self.client.prompts, [])


if __name__ == "__main__":
    unittest.main()
