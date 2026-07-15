from __future__ import annotations

import unittest
from unittest.mock import Mock

from core.brain import BrainExecutor, BrainRouter
from core.brain.fast_route import fast_route
from core.brain.planner import BrainPlanner
from core.tools import ToolRegistry
from core.tools.base import Tool


class _Tool(Tool):
    name = "weather"

    def __init__(self, result=None, error=None):
        self.result = result or {"type": "weather", "raw": {"temp": 18}, "source": "api"}
        self.error = error

    def match(self, query): return True

    def run(self, query):
        if self.error:
            raise self.error
        return self.result


class _SystemTool(Tool):
    name = "system"

    def __init__(self):
        self.calls = []

    def match(self, query): return True

    def run(self, query):
        raise AssertionError("structured system actions must use execute")

    def execute(self, action, params):
        self.calls.append((action, params))
        return {"type": "system", "raw": {
            "ok": True,
            "operation": action,
            "resolved_path": "C:/Users/demo/Desktop",
            "workspace_id": "Desktop",
            "result_count": 1,
            "items": [{"name": "note.md", "path": "C:/Users/demo/Desktop/note.md", "type": "file"}],
        }, "source": "local"}


class BrainExecutorTests(unittest.TestCase):
    def test_executes_normal_tool_step_without_mutating_result(self):
        tool_result = {"type": "weather", "raw": {"temp": 18}, "source": "api", "text": "hidden"}
        executor = BrainExecutor(ToolRegistry([_Tool(tool_result)]))

        execution = executor.execute({"steps": [{
            "tool": "weather", "params": {"query": "today"},
        }]}, "weather")[0]

        self.assertTrue(execution["ok"])
        self.assertEqual(execution["data"]["raw"]["temp"], 18)
        self.assertNotIn("text", execution["data"])
        self.assertEqual(tool_result["text"], "hidden")

    def test_tool_exception_becomes_structured_error(self):
        executor = BrainExecutor(ToolRegistry([_Tool(error=RuntimeError("offline"))]))

        execution = executor.execute({"steps": [{"tool": "weather", "params": {}}]}, "weather")[0]

        self.assertFalse(execution["ok"])
        self.assertEqual(execution["data"], {
            "type": "weather", "raw": {"error": "offline"}, "source": "local",
        })

    def test_router_delegates_plan_execution(self):
        client = Mock()
        intent_router = Mock()
        intent_router.classify.return_value = "task"
        planner = Mock()
        plan = {"goal": "weather", "steps": []}
        planner.plan_for_intent.return_value = plan
        executor = Mock()
        executions = [{"index": 0, "tool": "weather", "ok": True, "data": {}}]
        executor.execute.return_value = executions
        synthesizer = Mock()
        synthesizer.synthesize.return_value = {"text": "done"}
        memory = Mock()
        memory.prompt_context.return_value = ""
        router = BrainRouter(client, client, ToolRegistry(), memory, planner=planner,
                             synthesizer=synthesizer, intent_router=intent_router,
                             executor=executor)

        result = router.route("weather", [])

        self.assertEqual(result, {"text": "done"})
        executor.execute.assert_called_once_with(plan, "weather")
        self.assertIs(synthesizer.synthesize.call_args.args[3], executions)

    def test_file_search_pattern_and_structured_fields_survive_executor(self):
        tool = _SystemTool()
        executor = BrainExecutor(ToolRegistry([tool]))
        plan = {"steps": [{"tool": "system", "params": {
            "operation": "search_files",
            "source": "桌面",
            "pattern": "*.md",
            "resolved_path": "forged",
        }}]}

        execution = executor.execute(plan, "列出桌面上的 md 文件")[0]

        self.assertTrue(execution["ok"])
        self.assertEqual(tool.calls[0], ("search_files", {
            "operation": "search_files", "source": "桌面", "pattern": "*.md",
        }))
        raw = execution["data"]["raw"]
        self.assertEqual(raw["resolved_path"], "C:/Users/demo/Desktop")
        self.assertEqual(raw["workspace_id"], "Desktop")
        self.assertEqual(raw["result_count"], 1)
        self.assertEqual(raw["items"][0]["name"], "note.md")

    def test_file_mutation_fields_survive_but_authorization_fields_do_not(self):
        tool = _SystemTool()
        executor = BrainExecutor(ToolRegistry([tool]))
        plan = {"steps": [{"tool": "system", "params": {
            "operation": "replace_exact", "source": "config.txt",
            "old_text": "timeout=30", "new_text": "timeout=60",
            "confirmed": True, "risk": "low", "fingerprint": "forged",
        }}]}

        executor.execute(plan, "把 timeout=30 改成 timeout=60")

        self.assertEqual(tool.calls[0], ("replace_exact", {
            "operation": "replace_exact", "source": "config.txt",
            "old_text": "timeout=30", "new_text": "timeout=60",
        }))

    def test_successful_file_read_adds_task_continuation_without_forwarding_goal(self):
        tool = _SystemTool()
        tool.execute = lambda action, params: {
            "type": "system", "source": "local", "raw": {
                "ok": True, "operation": action, "path": params.get("source"),
                "file_type": "text", "content": "file body",
            },
        }
        executor = BrainExecutor(ToolRegistry([tool]))

        execution = executor.execute({"steps": [{"tool": "system", "params": {
            "operation": "read_file", "source": "test.txt", "goal": "summary",
        }}]}, "读取test.txt总结一下")[0]

        self.assertEqual(execution["continuation"], {
            "type": "file_content", "content": "file body",
            "file_type": "text", "next_action": "summary", "path": "test.txt",
        })

    def test_failed_file_read_never_adds_task_continuation(self):
        tool = _SystemTool()
        tool.execute = lambda action, params: {
            "type": "system", "source": "local", "raw": {
                "ok": False, "operation": action, "error_code": "path_not_found",
                "message": "missing", "content": "",
            },
        }
        executor = BrainExecutor(ToolRegistry([tool]))

        execution = executor.execute({"steps": [{"tool": "system", "params": {
            "operation": "read_file", "source": "missing.txt", "goal": "analysis",
        }}]}, "分析missing.txt")[0]

        self.assertNotIn("continuation", execution)

    def test_file_failure_has_structured_recovery_observation(self):
        tool = _SystemTool()
        tool.execute = lambda action, params: {
            "type": "system", "source": "local", "raw": {
                "ok": False, "operation": action, "path": params.get("source"),
                "error_code": "path_not_found", "message": "missing", "data": None,
            },
        }

        execution = BrainExecutor(ToolRegistry([tool])).execute({"steps": [{
            "tool": "system", "params": {"operation": "read_file", "source": "missing.txt"},
        }]}, "read missing.txt")[0]
        raw = execution["data"]["raw"]

        self.assertFalse(raw["ok"])
        self.assertEqual(raw["observation"], "file_not_found")
        self.assertTrue(raw["recoverable"])
        self.assertIn("search_similar_file", raw["suggestions"])

    def test_security_failure_is_not_recoverable(self):
        tool = _SystemTool()
        tool.execute = lambda action, params: {
            "type": "system", "source": "local", "raw": {
                "ok": False, "operation": action, "error_code": "protected_path",
                "message": "blocked", "data": None,
            },
        }

        execution = BrainExecutor(ToolRegistry([tool])).execute({"steps": [{
            "tool": "system", "params": {"operation": "read_file", "source": "blocked"},
        }]}, "read blocked")[0]

        self.assertFalse(execution["data"]["raw"]["recoverable"])
        self.assertEqual(execution["data"]["raw"]["suggestions"], [])

    def test_recovery_read_uses_existing_confirmation_and_strips_recovery_fields(self):
        class ConfirmingSystem(_SystemTool):
            def __init__(self):
                super().__init__()
                self.confirmation_callback = lambda action, params: True

        tool = ConfirmingSystem()
        executor = BrainExecutor(ToolRegistry([tool]))

        executor.execute({"steps": [{"tool": "system", "params": {
            "operation": "read_file", "source": "candidate.docx", "goal": "summary",
            "recovery_requires_confirmation": True,
            "recovery_original_path": "missing.md",
        }}]}, "summarize missing.md")

        forwarded = tool.calls[0][1]
        self.assertNotIn("recovery_requires_confirmation", forwarded)
        self.assertNotIn("recovery_original_path", forwarded)
        self.assertNotIn("confirmed", forwarded)

    def test_recovery_read_without_approval_does_not_call_tool(self):
        class RejectingSystem(_SystemTool):
            def __init__(self):
                super().__init__()
                self.confirmation_callback = lambda action, params: False

        tool = RejectingSystem()
        execution = BrainExecutor(ToolRegistry([tool])).execute({"steps": [{
            "tool": "system", "params": {
                "operation": "read_file", "source": "candidate.docx",
                "recovery_requires_confirmation": True,
            },
        }]}, "read candidate")[0]

        self.assertEqual(tool.calls, [])
        self.assertFalse(execution["ok"])
        self.assertEqual(execution["data"]["raw"]["error_code"], "user_cancelled")

    def test_natural_language_file_queries_route_to_structured_file_actions(self):
        access = fast_route("你现在能看哪个文件夹")
        listing = fast_route("列出桌面上的 md 文件")

        self.assertEqual(access["task_type"], "file")
        self.assertEqual(access["entities"]["operation"], "describe_file_access")
        self.assertEqual(listing["entities"]["operation"], "search_files")
        self.assertEqual(listing["entities"]["source"], "桌面")
        self.assertEqual(listing["entities"]["pattern"], "*.md")

        plan = BrainPlanner().plan_route("列出桌面上的 md 文件", listing)
        self.assertEqual(plan["steps"][0]["params"]["pattern"], "*.md")


if __name__ == "__main__":
    unittest.main()
