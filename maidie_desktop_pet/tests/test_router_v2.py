from __future__ import annotations

import unittest

from ai.client import AIClient, normalize_response
from ai.router import AIRouter
from core.agent import AgentCore, IntentDetector, Planner, ToolExecutor
from core.tools import ToolRegistry
from core.tools.base import Tool


class Memory:
    def prompt_context(self): return ""
    def load_memories(self, limit=20): return []
    def get_recent(self): return []


class Client(AIClient):
    source = "chat"
    def __init__(self): self.calls = 0
    def plan_task(self, message, memory_context): return None
    def ask(self, prompt, context):
        self.calls += 1
        return normalize_response({"text": "已基于工具数据完成回答"}, "chat")


class DataTool(Tool):
    def __init__(self, name, calls): self.name, self.calls = name, calls
    def match(self, query):
        return (self.name == "weather" and "天气" in query) or (self.name == "time" and "几点" in query)
    def run(self, query):
        self.calls.append(self.name)
        raw = ({"temperature": 18, "wind": 3.2, "forecast": "sunny", "date": "tomorrow"}
               if self.name == "weather" else {"iso": "2026-07-01T12:00:00+08:00"})
        return {"type": self.name, "raw": raw, "source": "api" if self.name == "weather" else "local"}


class Search:
    def handle(self, query): return {"ok": False, "error": "disabled"}


class RouterV2AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.client = Client()
        self.registry = ToolRegistry([DataTool("time", self.calls), DataTool("weather", self.calls)])
        self.agent = AgentCore(IntentDetector(self.registry), Planner(self.client),
                               ToolExecutor(self.registry, Search(), Memory()), Memory())
        self.router = AIRouter(self.client, self.client, tool_registry=self.registry, agent_core=self.agent)

    def test_running_decision_forces_planner_weather_and_synthesizer(self):
        plan = self.agent.plan_task("明天适合跑步吗", decision=True)
        self.assertGreaterEqual(len(plan["steps"]), 2)
        self.assertEqual([step["tool"] for step in plan["steps"]], ["weather", "llm"])
        result = self.router.ask("明天适合跑步吗", [])
        self.assertEqual(self.calls, ["weather"])
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(result["source"], "tool+llm")

    def test_weather_fact_uses_tool_then_synthesizer(self):
        result = self.router.ask("长沙明天天气怎么样", [])
        self.assertEqual(self.calls, ["weather"])
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(result["source"], "tool+llm")

    def test_time_fact_never_bypasses_tool(self):
        self.router.ask("现在几点", [])
        self.assertEqual(self.calls, ["time"])
        self.assertEqual(self.client.calls, 1)

    def test_gym_decision_has_two_steps(self):
        plan = self.agent.plan_task("要不要去健身", decision=True)
        self.assertGreaterEqual(len(plan["steps"]), 2)
        self.assertEqual(plan["steps"][-1]["tool"], "llm")

    def test_missing_required_data_blocks_llm_guess(self):
        router = AIRouter(self.client, self.client, tool_registry=ToolRegistry(),
                          agent_core=AgentCore(IntentDetector(ToolRegistry()), Planner(self.client),
                                               ToolExecutor(ToolRegistry(), Search(), Memory()), Memory()))
        result = router.ask("明天天气怎么样", [])
        self.assertEqual(result["text"], "不确定，需要查询。")
        self.assertEqual(self.client.calls, 0)

    def test_tool_stream_emits_only_visible_text(self):
        class NestedClient(Client):
            def ask(self, prompt, context):
                self.calls += 1
                return normalize_response({
                    "text": '{"text":"现在是晚上11点51分。","emotion":"温柔",'
                            '"action":"看怀表","state":"standby"}'
                }, "chat")

        client = NestedClient()
        agent = AgentCore(IntentDetector(self.registry), Planner(client),
                          ToolExecutor(self.registry, Search(), Memory()), Memory())
        router = AIRouter(client, client, tool_registry=self.registry, agent_core=agent)
        chunks = []
        result = router.ask_stream("现在几点", [], chunks.append)
        self.assertEqual(chunks, ["现在是晚上11点51分。"])
        self.assertEqual(result["text"], "现在是晚上11点51分。")
        self.assertNotIn("{", "".join(chunks))


if __name__ == "__main__":
    unittest.main()
