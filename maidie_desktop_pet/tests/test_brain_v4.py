from __future__ import annotations

import unittest

from ai.client import AIClient, normalize_response
from core.brain import BrainPlanner, BrainRouter, IntentClassifier, LLMIntentRouter, Synthesizer
from core.tools import MemoryTool, ScreenTool, SearchTool, TimeTool, ToolRegistry
from core.tools.base import Tool


class Client(AIClient):
    def __init__(self, text="结果已经准备好了"):
        self.text, self.prompts, self.intent_prompts = text, [], []

    def ask(self, prompt, context):
        self.prompts.append(prompt)
        return normalize_response({"text": self.text, "emotion": "happy",
                                   "action": "talk", "state": "talking"}, "chat")

    def route_intent(self, prompt, context):
        self.intent_prompts.append(prompt)
        if "你能看到我屏幕吗" in prompt or "我在做什么" in prompt or "我在干嘛" in prompt:
            return {"intent": "screen", "confidence": 0.95, "reason": "desktop state request"}
        if "帮我修bug" in prompt:
            return {"intent": "code_task", "confidence": 0.95, "reason": "debug request"}
        if "明天适合跑步吗" in prompt or "天气" in prompt or "几点" in prompt:
            return {"intent": "task", "confidence": 0.9, "reason": "tool facts needed"}
        return {"intent": "chat", "confidence": 0.8, "reason": "conversation"}


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

    def test_llm_router_intent(self):
        router = LLMIntentRouter(self.client, IntentClassifier())
        self.assertEqual(router.classify("明天适合跑步吗"), "task")
        self.assertEqual(router.classify("你能看到我屏幕吗"), "screen")
        self.assertEqual(router.classify("帮我修bug"), "code_task")
        self.assertEqual(router.classify("好无聊"), "chat")
        self.assertTrue(all("You are the intent router" in prompt for prompt in self.client.intent_prompts))

    def test_regex_only_when_llm_router_fails(self):
        class BrokenClient(Client):
            def route_intent(self, prompt, context):
                raise RuntimeError("offline")

        router = LLMIntentRouter(BrokenClient(), IntentClassifier())
        self.assertEqual(router.classify("你能看到我屏幕吗"), "screen")
        self.assertEqual(router.last_route["source"], "fallback")

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
        result = self.router.ask("你能看到我屏幕吗", [])
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
