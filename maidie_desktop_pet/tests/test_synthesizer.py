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


class EchoFileClient:
    api_key = "configured"

    def ask(self, _prompt, _context):
        return {"text": "RAW FILE BODY", "emotion": "thinking",
                "action": "talk", "state": "talking"}


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


    def test_file_tool_failure_does_not_claim_directory_was_seen(self):
        synthesizer = Synthesizer(OfflineClient())
        data = {"type": "system", "source": "local", "raw": {
            "ok": False,
            "operation": "list_directory",
            "error_code": "PATH_NOT_RESOLVED",
            "message": "system directory is not available: 桌面",
            "data": None,
            "items": None,
            "result_count": None,
        }}

        result = synthesizer.synthesize(
            "查看我桌面有哪些文件", "system_task", None,
            [{"tool": "system", "ok": False, "data": data}], "", [],
        )

        self.assertIn("没有成功访问", result["text"])
        self.assertIn("PATH_NOT_RESOLVED", result["text"])
        self.assertNotIn("没有找到", result["text"])
        self.assertNotIn("快捷方式", result["text"])

    def test_file_tool_empty_success_can_say_no_matches(self):
        synthesizer = Synthesizer(OfflineClient())
        data = {"type": "system", "source": "local", "raw": {
            "ok": True,
            "operation": "search_files",
            "resolved_path": "C:/Users/demo/Desktop",
            "workspace_id": "Desktop",
            "result_count": 0,
            "items": [],
            "error_code": None,
            "message": "",
        }}

        result = synthesizer.synthesize(
            "列出桌面上的 md 文件", "system_task", None,
            [{"tool": "system", "ok": True, "data": data}], "", [],
        )

        self.assertIn("没有找到", result["text"])
        self.assertIn("C:/Users/demo/Desktop", result["text"])

    def test_file_tool_listing_uses_structured_items_only(self):
        synthesizer = Synthesizer(OfflineClient())
        data = {"type": "system", "source": "local", "raw": {
            "ok": True,
            "operation": "search_files",
            "resolved_path": "C:/Users/demo/Desktop",
            "workspace_id": "Desktop",
            "result_count": 1,
            "items": [{"name": "actual.md", "path": "C:/Users/demo/Desktop/actual.md", "type": "file"}],
            "error_code": None,
            "message": "",
        }}

        result = synthesizer.synthesize(
            "列出桌面上的 md 文件", "system_task", None,
            [{"tool": "system", "ok": True, "data": data}], "", [],
        )
        text = result.get("panel_text", "") + result["text"]

        self.assertIn("actual.md", text)
        self.assertNotIn("快捷方式", text)

    def test_file_access_response_reports_permissions(self):
        synthesizer = Synthesizer(OfflineClient())
        data = {"type": "system", "source": "local", "raw": {
            "ok": True,
            "operation": "describe_file_access",
            "workspaces": [
                {"workspace_id": "primary", "name": "Primary", "root": "C:/project",
                 "mode": "read_write", "readable": True, "writable": True, "explicit": True},
                {"workspace_id": "home-readonly", "name": "Home", "root": "C:/Users/demo",
                 "mode": "read_only", "readable": True, "writable": False, "explicit": False},
            ],
            "system_directories": [
                {"id": "desktop", "name": "Desktop", "path": "C:/Users/demo/Desktop",
                 "accessible": True, "mode": "read_only", "workspace_id": "home-readonly"},
                {"id": "documents", "name": "Documents", "path": "C:/Users/demo/Documents",
                 "accessible": True, "mode": "read_only", "workspace_id": "home-readonly"},
                {"id": "downloads", "name": "Downloads", "path": "C:/Users/demo/Downloads",
                 "accessible": False, "mode": None, "workspace_id": None},
            ],
        }}

        result = synthesizer.synthesize(
            "你现在能看哪个文件夹", "system_task", None,
            [{"tool": "system", "ok": True, "data": data}], "", [],
        )
        text = result.get("panel_text", "") + result["text"]

        self.assertIn("C:/project", text)
        self.assertIn("只读", text)
        self.assertIn("Downloads 不可访问", text)

    def test_file_write_and_delete_failures_cannot_be_presented_as_success(self):
        synthesizer = Synthesizer(OfflineClient())
        for operation in ("append_file", "replace_exact", "delete_file"):
            data = {"type": "system", "source": "local", "raw": {
                "ok": False, "operation": operation, "path": "C:/project/a.txt",
                "error_code": "user_cancelled", "message": "用户取消了操作",
                "result": None,
            }}
            result = synthesizer.synthesize(
                "执行文件操作", "system_task", None,
                [{"tool": "system", "ok": False, "data": data}], "", [],
            )
            self.assertIn("没有成功", result["text"])
            self.assertNotIn("已经完成", result["text"])

    def test_successful_document_read_uses_tool_content(self):
        synthesizer = Synthesizer(OfflineClient())
        data = {"type": "system", "source": "local", "raw": {
            "ok": True, "operation": "read_file", "path": "C:/project/report.pdf",
            "file_type": "pdf", "content": "Page one fact", "error_code": None,
            "message": "", "result": {"metadata": {"pages": 1}},
        }}

        result = synthesizer.synthesize(
            "读取报告", "system_task", None,
            [{"tool": "system", "ok": True, "data": data}], "", [],
        )

        self.assertIn("Page one fact", result["text"])

    def test_file_continuation_rejects_model_echo_of_full_source_content(self):
        synthesizer = Synthesizer(EchoFileClient())
        data = {"type": "system", "source": "local", "raw": {
            "ok": True, "operation": "read_file", "path": "test.txt",
            "file_type": "text", "content": "RAW FILE BODY",
        }}

        result = synthesizer.synthesize(
            "读取test.txt总结一下", "system_task", {"task_goal": "summary"},
            [{"tool": "system", "ok": True, "data": data, "continuation": {
                "type": "file_content", "content": "RAW FILE BODY",
                "file_type": "text", "next_action": "summary", "path": "test.txt",
            }}], "", [],
        )

        rendered = str(result.get("panel_text") or result["text"])
        self.assertNotIn("RAW FILE BODY", rendered)
        self.assertIn("不能可靠完成总结", rendered)


if __name__ == "__main__": unittest.main()
