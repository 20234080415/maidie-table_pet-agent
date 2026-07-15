from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.brain import BrainExecutor, BrainPlanner
from core.tools import CodingAgentTool, ToolRegistry


class CodingAgentToolTests(unittest.TestCase):
    def options(self, **overrides):
        values = {"enabled": True, "provider": "opencode", "command": "opencode",
                  "startup_timeout_seconds": 2, "total_timeout_seconds": 5,
                  "no_progress_timeout_seconds": 3, "dry_run": True}
        values.update(overrides)
        return values

    def test_workspace_not_configured_is_rejected(self):
        result = CodingAgentTool({}, self.options()).run("分析项目")
        self.assertEqual(result["raw"]["error_code"], "workspace_not_configured")

    def test_configuration_validation_statuses(self):
        missing = CodingAgentTool.validate_configuration("", "opencode", "opencode", True)
        self.assertEqual(missing["code"], "workspace_not_configured")
        with tempfile.TemporaryDirectory() as root:
            unsupported = CodingAgentTool.validate_configuration(
                root, "other", "other", True
            )
            self.assertEqual(unsupported["code"], "provider_unsupported")
            unsafe = CodingAgentTool.validate_configuration(root, "opencode", "opencode", False)
            self.assertEqual(unsafe["code"], "configuration_invalid")
            with patch("core.tools.coding_agent_tool.shutil.which", return_value=None):
                unavailable = CodingAgentTool.validate_configuration(
                    root, "opencode", "missing", True
                )
            self.assertEqual(unavailable["code"], "command_unavailable")
            with patch("core.tools.coding_agent_tool.shutil.which", return_value="opencode"):
                available = CodingAgentTool.validate_configuration(
                    root, "opencode", "opencode", True
                )
            self.assertEqual(available, {"ok": True, "code": "available", "message": "可用"})

    def test_path_outside_workspace_is_rejected(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            result = CodingAgentTool({"root": root}, self.options()).run(
                "解释模块", "explain_module", outside,
            )
        self.assertEqual(result["raw"]["error_code"], "path_outside_workspace")

    def test_disabled_is_rejected(self):
        result = CodingAgentTool({}, self.options(enabled=False)).run("分析项目")
        self.assertEqual(result["raw"]["error_code"], "disabled")

    @patch("core.tools.coding_agent_tool.shutil.which", return_value=None)
    def test_missing_cli_returns_structured_error(self, _which):
        with tempfile.TemporaryDirectory() as root:
            result = CodingAgentTool({"root": root}, self.options()).run("分析项目")
        self.assertEqual(result["type"], "coding_agent")
        self.assertEqual(result["raw"]["error_code"], "cli_not_found")

    @patch("core.tools.coding_agent_tool.shutil.which", return_value="opencode")
    def test_subprocess_never_uses_shell(self, _which):
        with tempfile.TemporaryDirectory() as root:
            tool = CodingAgentTool({"root": root}, self.options())
            tool.runner.run = Mock(return_value={"status": "completed", "returncode": 0,
                "stdout": '{"summary":"ok"}', "stdout_tail": '{"summary":"ok"}',
                "stderr_tail": "", "log_path": "agent.log"})
            CodingAgentTool._command("opencode", "opencode", "prompt")
            tool.run("分析项目")
            self.assertEqual(Path(tool.runner.run.call_args.args[1]), Path(root).resolve())
            self.assertEqual(tool.runner.run.call_args.kwargs["startup_timeout"], 2)
            self.assertEqual(tool.runner.run.call_args.kwargs["total_timeout"], 5)
            self.assertEqual(tool.runner.run.call_args.kwargs["no_progress_timeout"], 3)
            self.assertEqual(tool.runner.run.call_args.args[0][2:4], ["--format", "json"])
            permissions = json.loads(
                tool.runner.run.call_args.kwargs["env"]["OPENCODE_CONFIG_CONTENT"]
            )["permission"]
            self.assertEqual(permissions["external_directory"], "deny")
            self.assertEqual(permissions["edit"], "deny")
            self.assertEqual(permissions["bash"], "deny")
            self.assertEqual(tool.runner.run.call_args.kwargs["env"]["NO_COLOR"], "1")

    @patch("core.tools.coding_agent_tool.shutil.which", return_value="codex")
    def test_codex_is_forced_into_read_only_sandbox(self, _which):
        with tempfile.TemporaryDirectory() as root:
            options = self.options(provider="codex", command="codex")
            tool = CodingAgentTool({"root": root}, options)
            tool.runner.run = Mock(return_value={"status": "completed", "returncode": 0,
                "stdout": '{"summary":"ok"}', "stdout_tail": '{"summary":"ok"}',
                "stderr_tail": "", "log_path": "agent.log"})
            tool.run("分析项目")
        args = tool.runner.run.call_args.args[0]
        self.assertIn("read-only", args)
        self.assertEqual(args[-1], "-")
        self.assertIn("read-only analysis mode", tool.runner.run.call_args.kwargs["input_text"])

    @patch("core.tools.coding_agent_tool.shutil.which", return_value="opencode")
    def test_total_timeout_returns_structured_error(self, _which):
        with tempfile.TemporaryDirectory() as root:
            tool = CodingAgentTool({"root": root}, self.options())
            tool.runner.run = Mock(return_value={"status": "total_timeout", "returncode": None,
                "stdout_tail": "", "stderr_tail": "", "killed_process_tree": True})
            result = tool.run("分析项目")
        self.assertEqual(result["raw"]["error_code"], "total_timeout")

    @patch("core.tools.coding_agent_tool.shutil.which", return_value="opencode")
    def test_dry_run_does_not_write_workspace_files(self, _which):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / "marker.py"
            marker.write_text("before", encoding="utf-8")
            tool = CodingAgentTool({"root": root}, self.options())
            tool.runner.run = Mock(return_value={"status": "completed", "returncode": 0,
                "stdout": '{"summary":"read only"}',
                "stdout_tail": '{"summary":"read only"}', "stderr_tail": ""})
            tool.run("生成 patch", "propose_patch")
            self.assertEqual(marker.read_text(encoding="utf-8"), "before")
            self.assertEqual(list(Path(root).iterdir()), [marker])

    def test_fenced_json_output_is_parsed_as_structured_analysis(self):
        raw = CodingAgentTool()._raw("analyze_project")
        CodingAgentTool._merge_output(
            raw,
            '```json\n{"summary":"完成","findings":["问题"],'
            '"suggested_changes":["建议"],"tests_suggested":["测试"]}\n```',
        )
        self.assertEqual(raw["summary"], "完成")
        self.assertEqual(raw["findings"], ["问题"])
        self.assertEqual(raw["parse_status"], "parsed")
        self.assertEqual(raw["parse_error"], "")
        self.assertNotIn("```", raw["summary"])

    def test_broken_json_preserves_raw_output_and_parse_error(self):
        raw = CodingAgentTool()._raw("analyze_project")
        CodingAgentTool._merge_output(raw, '{"summary":"broken"')
        self.assertEqual(raw["parse_status"], "error")
        self.assertIn("JSON", raw["parse_error"])
        self.assertEqual(raw["raw_output"], '{"summary":"broken"')
        self.assertEqual(raw["summary"], "")

    def test_json_object_is_recovered_from_surrounding_explanation(self):
        raw = CodingAgentTool()._raw("analyze_project")
        CodingAgentTool._merge_output(
            raw,
            '分析如下：\n{"summary":"完成","findings":[]}\n以上。',
        )
        self.assertEqual(raw["parse_status"], "parsed")
        self.assertEqual(raw["summary"], "完成")

    @patch("core.tools.coding_agent_tool.shutil.which", return_value="opencode")
    def test_start_and_progress_are_forwarded_as_visible_output_events(self, _which):
        events = []
        with tempfile.TemporaryDirectory() as root:
            tool = CodingAgentTool({"root": root}, self.options())

            def fake_run(*args, **kwargs):
                kwargs["on_start"]({"status": "running", "pid": 321})
                kwargs["on_status_change"]({
                    "status": "running", "content": "正在分析项目...\n已运行 5 秒",
                })
                return {
                    "status": "completed", "returncode": 0,
                    "stdout": '{"summary":"ok"}',
                    "stdout_tail": '{"summary":"ok"}', "stderr_tail": "",
                }

            tool.runner.run = fake_run
            tool.run("分析项目", on_event=events.append)
        progress = [event for event in events if event["mode"] == "TASK_PROGRESS"]
        self.assertIn("Coding Agent 已启动\nPID: 321", progress[0]["content"])
        self.assertIn("已运行 5 秒", progress[1]["content"])
        self.assertEqual(progress[0]["phase"], "running")
        self.assertEqual(progress[1]["phase"], "heartbeat")

    @patch("core.tools.coding_agent_tool.shutil.which", return_value="opencode")
    def test_opencode_jsonl_filters_large_tool_payload_and_parses_text_event(self, _which):
        events = []
        direct_events = []
        huge_file = "source line\n" * 2000
        tool_event = json.dumps({
            "type": "tool_use",
            "part": {
                "tool": "read",
                "state": {
                    "status": "completed",
                    "input": {"filePath": "C:/workspace/core/app.py"},
                    "output": huge_file,
                },
            },
        }, ensure_ascii=False)
        final_text = '```json\n{"summary":"完成","findings":["问题"]}\n```'
        text_event = json.dumps({
            "type": "text", "part": {"type": "text", "text": final_text},
        }, ensure_ascii=False)
        stdout = tool_event + "\n" + text_event + "\n"

        with tempfile.TemporaryDirectory() as root:
            tool = CodingAgentTool({"root": root}, self.options())
            tool.set_progress_callbacks(on_output_line=direct_events.append)

            def fake_run(*args, **kwargs):
                midpoint = len(tool_event) // 2
                kwargs["on_output_line"]({
                    "stream": "stdout", "line": tool_event[:midpoint],
                })
                kwargs["on_output_line"]({
                    "stream": "stdout",
                    "line": tool_event[midpoint:] + "\n" + text_event + "\n",
                })
                return {
                    "status": "completed", "returncode": 0,
                    "stdout": stdout, "stdout_tail": stdout[-200:],
                    "stderr_tail": "", "log_path": "agent.log",
                }

            tool.runner.run = fake_run
            result = tool.run("分析项目", on_event=events.append)

        visible = [event["content"] for event in events if event["type"] == "token"]
        self.assertTrue(any("app.py" in content for content in visible))
        self.assertTrue(any("已生成结构化结果" in content for content in visible))
        self.assertFalse(any("source line" in content for content in visible))
        self.assertTrue(all(len(content) < 200 for content in visible))
        self.assertEqual(direct_events, [])
        self.assertEqual(result["raw"]["parse_status"], "parsed")
        self.assertEqual(result["raw"]["summary"], "完成")
        self.assertNotIn("stdout", result["raw"]["process"])

    @patch("core.tools.coding_agent_tool.shutil.which", return_value="opencode")
    def test_opencode_stderr_remains_visible_without_raw_json_stdout(self, _which):
        events = []
        with tempfile.TemporaryDirectory() as root:
            tool = CodingAgentTool({"root": root}, self.options())

            def fake_run(*args, **kwargs):
                event = json.dumps({
                    "type": "text",
                    "part": {"type": "text", "text": '{"summary":"ok"}'},
                }) + "\n"
                kwargs["on_output_line"]({"stream": "stdout", "line": event})
                kwargs["on_output_line"]({"stream": "stderr", "line": "err"})
                return {
                    "status": "completed", "returncode": 0,
                    "stdout": event,
                    "stdout_tail": event, "stderr_tail": "err",
                }

            tool.runner.run = fake_run
            result = tool.run("分析项目", on_event=events.append)
        contents = [event["content"] for event in events if event["type"] == "token"]
        self.assertIn("err", contents)
        self.assertFalse(any('"type": "text"' in content for content in contents))
        self.assertEqual(result["raw"]["summary"], "ok")

    def test_executor_allows_registered_coding_agent(self):
        with tempfile.TemporaryDirectory() as root:
            tool = CodingAgentTool({"root": root}, self.options(enabled=False))
            result = BrainExecutor(ToolRegistry([tool])).execute({"steps": [{
                "tool": "coding_agent", "params": {"operation": "analyze_project"},
            }]}, "分析我的项目")[0]
        self.assertEqual(result["data"]["raw"]["error_code"], "disabled")
        self.assertNotEqual(result["data"]["raw"]["error"], "tool blocked by executor")


class CodingAgentPlannerTests(unittest.TestCase):
    def test_code_requests_route_to_coding_agent(self):
        planner = BrainPlanner()
        cases = {
            "分析我的项目": "analyze_project",
            "你调用open'co'de看看我分析一下我的这个项目": "analyze_project",
            "使用 OpenCode 检查当前项目": "analyze_project",
            "帮我修这个 bug": "propose_fix",
            "这个模块怎么重构": "explain_module",
            "帮我生成 patch": "propose_patch",
            "帮我看看测试怎么写": "test_plan",
            "这个功能应该加在哪里": "explain_module",
        }
        for query, operation in cases.items():
            with self.subTest(query=query):
                step = planner.plan_for_intent(query, "code_task")["steps"][0]
                self.assertEqual(step["tool"], "coding_agent")
                self.assertEqual(step["params"]["operation"], operation)

    def test_normal_chat_does_not_trigger_coding_agent(self):
        plan = BrainPlanner().plan_for_intent("今天心情怎么样", "chat")
        self.assertNotIn("coding_agent", {step["tool"] for step in plan["steps"]})


if __name__ == "__main__":
    unittest.main()
