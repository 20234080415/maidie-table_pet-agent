from __future__ import annotations

import unittest
from unittest.mock import Mock

from core.brain import BrainExecutor, BrainRouter
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


if __name__ == "__main__":
    unittest.main()
