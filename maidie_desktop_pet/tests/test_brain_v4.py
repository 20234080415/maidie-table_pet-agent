from __future__ import annotations

import unittest

from ai.client import AIClient, normalize_response
from core.brain import BrainPlanner, BrainRouter, IntentClassifier, Synthesizer
from core.tools import MemoryTool, ScreenTool, SearchTool, TimeTool, ToolRegistry
from core.tools.base import Tool


class Client(AIClient):
    def __init__(self, text="结果已经准备好了"):
        self.text, self.prompts = text, []

    def ask(self, prompt, context):
        self.prompts.append(prompt)
        return normalize_response({"text": self.text, "emotion": "happy",
                                   "action": "talk", "state": "talking"}, "chat")


class Memory:
    def prompt_context(self): return "用户喜欢简洁回复"
    def load_memories(self, limit=20): return [{"key": "style", "value": "简洁"}]
    def get_recent(self): return [{"message": "早", "response": "早呀"}]


class Network:
    def handle(self, query): return {"ok": True, "summary": "事实资料", "sources": []}


class Awareness:
    def __init__(self): self.calls = 0
    def screen_awareness_snapshot(self):
        self.calls += 1
        return {"screen_text": "def route():", "app": "Code", "window": "router.py",
                "context": "coding"}


class Weather(Tool):
    name = "weather"
    def match(self, query): return "天气" in query
    def run(self, query):
        return {"type": "weather", "raw": {"temp": 18, "forecast": "sunny"}, "source": "api"}


class BrainV4AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.client, self.memory, self.awareness = Client(), Memory(), Awareness()
        self.registry = ToolRegistry([
            TimeTool(), Weather(), SearchTool(Network()), ScreenTool(self.awareness),
            MemoryTool(self.memory),
        ])
        self.router = BrainRouter(self.client, self.client, self.registry, self.memory)

    def test_router_intent(self):
        classifier = IntentClassifier()
        self.assertEqual(classifier.classify("陪我聊会儿"), "chat")
        self.assertEqual(classifier.classify("现在几点"), "task")
        self.assertEqual(classifier.classify("你能看到我屏幕吗"), "screen")

    def test_planner_execution(self):
        plan = BrainPlanner().plan("明天天气适不适合跑步", self.memory)
        self.assertGreaterEqual(len(plan["steps"]), 2)
        self.assertEqual([step["tool"] for step in plan["steps"]], ["weather", "memory"])
        result = self.router.ask("明天天气适不适合跑步", [])
        self.assertEqual(result["source"], "tool")
        self.assertIn('"temp": 18', self.client.prompts[-1])

    def test_tool_data_only(self):
        results = [
            TimeTool().run("几点"),
            Weather().run("天气"),
            SearchTool(Network()).run("查资料"),
            ScreenTool(self.awareness).run("屏幕"),
            MemoryTool(self.memory).run("记忆"),
        ]
        for result in results:
            self.assertEqual(set(result), {"type", "raw", "source"})
            self.assertNotIn("text", result)

    def test_screen_pipeline(self):
        result = self.router.ask("我在做什么？", [])
        self.assertEqual(self.awareness.calls, 1)
        self.assertEqual(result["source"], "screen")
        self.assertIn('"context": "coding"', self.client.prompts[-1])

    def test_personality_preservation(self):
        result = self.router.ask("现在几点", [])
        self.assertTrue(result["text"].startswith("好啦好啦，"))
        self.assertNotRegex(result["text"], r"Router|Planner|tool|工具调用")
        self.assertEqual(set(result), {"text", "emotion", "action", "state", "source"})

    def test_chat_never_executes_tools(self):
        self.router.ask("今天心情怎么样呀", [])
        self.assertEqual(self.awareness.calls, 0)
        self.assertEqual(self.client.prompts[-1].count("工具数据：[]"), 1)


if __name__ == "__main__":
    unittest.main()
