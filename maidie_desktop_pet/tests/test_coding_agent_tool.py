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
                  "timeout_seconds": 5, "dry_run": True}
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
                "stdout_tail": '{"summary":"ok"}', "stderr_tail": ""})
            CodingAgentTool._command("opencode", "opencode", "prompt")
            tool.run("分析项目")
            self.assertEqual(Path(tool.runner.run.call_args.args[1]), Path(root).resolve())
            permissions = json.loads(
                tool.runner.run.call_args.kwargs["env"]["OPENCODE_CONFIG_CONTENT"]
            )["permission"]
            self.assertEqual(permissions["external_directory"], "deny")
            self.assertEqual(permissions["edit"], "deny")
            self.assertEqual(permissions["bash"], "deny")

    @patch("core.tools.coding_agent_tool.shutil.which", return_value="codex")
    def test_codex_is_forced_into_read_only_sandbox(self, _which):
        with tempfile.TemporaryDirectory() as root:
            options = self.options(provider="codex", command="codex")
            tool = CodingAgentTool({"root": root}, options)
            tool.runner.run = Mock(return_value={"status": "completed", "returncode": 0,
                "stdout_tail": '{"summary":"ok"}', "stderr_tail": ""})
            tool.run("分析项目")
        args = tool.runner.run.call_args.args[0]
        self.assertIn("read-only", args)
        self.assertEqual(args[-1], "-")
        self.assertIn("read-only analysis mode", tool.runner.run.call_args.kwargs["input_text"])

    @patch("core.tools.coding_agent_tool.shutil.which", return_value="opencode")
    def test_timeout_returns_structured_error(self, _which):
        with tempfile.TemporaryDirectory() as root:
            tool = CodingAgentTool({"root": root}, self.options())
            tool.runner.run = Mock(return_value={"status": "timeout", "returncode": None,
                "stdout_tail": "", "stderr_tail": "", "killed_process_tree": True})
            result = tool.run("分析项目")
        self.assertEqual(result["raw"]["error_code"], "timeout")

    @patch("core.tools.coding_agent_tool.shutil.which", return_value="opencode")
    def test_dry_run_does_not_write_workspace_files(self, _which):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / "marker.py"
            marker.write_text("before", encoding="utf-8")
            tool = CodingAgentTool({"root": root}, self.options())
            tool.runner.run = Mock(return_value={"status": "completed", "returncode": 0,
                "stdout_tail": '{"summary":"read only"}', "stderr_tail": ""})
            tool.run("生成 patch", "propose_patch")
            self.assertEqual(marker.read_text(encoding="utf-8"), "before")
            self.assertEqual(list(Path(root).iterdir()), [marker])

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
