"""Compatibility tests for the deprecated AIRouter/core.agent pipeline."""

from __future__ import annotations

import unittest

from ai.client import AIClient, normalize_response
from ai.router import AIRouter
from core.agent import AgentCore, IntentDetector, Planner, ToolExecutor
from core.awareness.context import AwarenessContext
from core.tools import ToolRegistry


class Memory:
    def prompt_context(self): return ""
    def load_memories(self, limit=20): return []
    def get_recent(self): return []


class Search:
    def handle(self, query): return {"ok": False}


class Client(AIClient):
    def __init__(self): self.prompts = []
    def plan_task(self, message, memory_context): return None
    def ask(self, prompt, context):
        self.prompts.append(prompt)
        return normalize_response({"text": "你正在 Visual Studio Code 中编写 Python 代码。"}, "chat")


class Mouse:
    state = "idle"
    class Idle: idle_time = 0
    idle_detector = Idle()


class Screen:
    def __init__(self): self.calls = []
    def read(self, force=False):
        self.calls.append(force)
        return {"screen_text": "def handle_input(user_input):", "context": "coding"}


class App:
    def __init__(self): self.calls = 0
    def snapshot(self):
        self.calls += 1
        return {"active_app": "Code", "app_type": "coding", "window_title": "router.py"}


class Window:
    def __init__(self): self.calls = 0
    def snapshot(self):
        self.calls += 1
        return {"window_state": "coding", "window_title": "router.py - Visual Studio Code"}


class ScreenAwarenessRouterTests(unittest.TestCase):
    def setUp(self):
        self.screen, self.app, self.window = Screen(), App(), Window()
        awareness = AwarenessContext(Mouse(), self.window, self.app, self.screen)
        registry, memory, client = ToolRegistry(), Memory(), Client()
        core = AgentCore(IntentDetector(registry), Planner(client),
                         ToolExecutor(registry, Search(), memory), memory, awareness)
        self.router, self.client = AIRouter(client, client, tool_registry=registry, agent_core=core), client

    def test_can_you_see_screen_forces_all_three_tools(self):
        result = self.router.ask("你能看到我屏幕吗？", [])
        self.assertEqual(self.screen.calls, [True])
        self.assertEqual((self.app.calls, self.window.calls), (1, 1))
        self.assertEqual(result["source"], "tool+llm")
        self.assertIn("screen_text", self.client.prompts[-1])

    def test_current_activity_is_coding_context(self):
        self.router.ask("我现在在干嘛？", [])
        self.assertIn('"context": "coding"', self.client.prompts[-1])

    def test_writing_code_question_cannot_bypass_tools(self):
        self.router.ask("你知道我在写代码吗？", [])
        self.assertEqual(self.screen.calls, [True])
        self.assertEqual(self.app.calls, 1)
        self.assertEqual(self.window.calls, 1)


if __name__ == "__main__":
    unittest.main()
