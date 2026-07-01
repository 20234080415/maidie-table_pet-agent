from __future__ import annotations

import unittest

from ai.client import AIClient, normalize_response
from core.agent import AgentCore, IntentDetector, Planner, ToolExecutor
from core.tools import TimeTool, ToolRegistry, WeatherTool
from core.tools.base import Tool


class FakeMemory:
    def __init__(self):
        self.background = "用户背景信息：喜欢简洁回答；正在学习嵌入式。"

    def prompt_context(self):
        return self.background

    def load_memories(self, limit=20):
        return [{"type": "preference", "key": "style", "value": "简洁"}]

    def get_recent(self):
        return [{"message": "我在学习嵌入式", "response": "记住啦"}]


class PlanningClient:
    def __init__(self, plan=None):
        self.plan = plan
        self.received_memory = ""

    def plan_task(self, message, memory_context):
        self.received_memory = memory_context
        return self.plan


class SynthesisClient(AIClient):
    source = "chat"

    def __init__(self):
        self.prompts = []

    def ask(self, prompt, context):
        self.prompts.append(prompt)
        return normalize_response({"text": "明天天气适合跑步。"}, "chat")


class RecordingTool(Tool):
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    def match(self, query):
        return self.name in query

    def run(self, query):
        self.calls.append(self.name)
        return {
            "type": self.name,
            "text": f"{self.name} result",
            "raw": {"value": self.name},
            "source": "local" if self.name == "time" else "api",
        }


class FakeSearch:
    enabled = True

    def __init__(self, calls):
        self.calls = calls

    def handle(self, query):
        self.calls.append("search")
        return {
            "ok": True, "type": "search", "title": "result",
            "summary": "search result", "sources": [], "error": "",
        }


class AgentCoreTests(unittest.TestCase):
    def test_intent_detection(self):
        detector = IntentDetector(ToolRegistry([TimeTool(), WeatherTool()]))
        self.assertEqual(detector.detect("陪我聊聊天"), "CHAT")
        self.assertEqual(detector.detect("现在几点"), "DIRECT_TOOL")
        self.assertEqual(detector.detect("长沙天气"), "DIRECT_TOOL")
        self.assertEqual(detector.detect("帮我查明天天气适不适合跑步"), "DECISION_TASK")
        self.assertEqual(detector.detect("要不要去健身"), "DECISION_TASK")

    def test_planner_output(self):
        planner = Planner(PlanningClient(None))
        result = planner.plan("帮我查明天天气适不适合跑步", "喜欢跑步")
        self.assertEqual(result["goal"], "帮我查明天天气适不适合跑步")
        self.assertGreaterEqual(len(result["steps"]), 1)
        self.assertIn("weather", [step["tool"] for step in result["steps"]])
        self.assertIn("llm", [step["tool"] for step in result["steps"]])
        for step in result["steps"]:
            self.assertEqual(set(step), {"tool", "action", "params"})

    def test_tool_execution_chain(self):
        calls = []
        registry = ToolRegistry([
            RecordingTool("time", calls), RecordingTool("weather", calls)
        ])
        executor = ToolExecutor(registry, FakeSearch(calls), FakeMemory())
        plan = {"goal": "test", "steps": [
            {"tool": "time", "action": "time", "params": {}},
            {"tool": "weather", "action": "weather", "params": {}},
            {"tool": "search", "action": "search", "params": {}},
            {"tool": "llm", "action": "summary", "params": {}},
        ]}
        results = executor.execute(plan, "query")
        self.assertEqual(calls, ["time", "weather", "search"])
        self.assertEqual(len(results), 4)
        self.assertTrue(all(item["ok"] for item in results))

    def test_memory_injection(self):
        client = PlanningClient({
            "goal": "goal",
            "steps": [{"tool": "llm", "action": "summary", "params": {}}],
        })
        memory = FakeMemory()
        planner = Planner(client)
        planner.plan("帮我总结", memory.prompt_context())
        self.assertEqual(client.received_memory, memory.background)

    def test_action_state_transition(self):
        memory = FakeMemory()
        planning_client = PlanningClient({
            "goal": "跑步建议",
            "steps": [
                {"tool": "weather", "action": "查天气", "params": {}},
                {"tool": "llm", "action": "给建议", "params": {}},
            ],
        })
        calls = []
        registry = ToolRegistry([RecordingTool("weather", calls)])
        agent = AgentCore(
            IntentDetector(registry),
            Planner(planning_client),
            ToolExecutor(registry, FakeSearch(calls), memory),
            memory,
        )
        result = agent.execute_task("帮我判断是否适合跑步", [], SynthesisClient())
        self.assertEqual(result["state"], "talking")
        self.assertEqual(result["source"], "tool+llm")
        self.assertEqual(result["action"], "talk")
        self.assertEqual(set(result), {"text", "emotion", "action", "state", "source"})


if __name__ == "__main__":
    unittest.main()
