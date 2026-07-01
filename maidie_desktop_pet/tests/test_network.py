from __future__ import annotations

import unittest

from ai.client import AIClient, normalize_response
from ai.router import AIRouter
from core.plugins.network import NetworkPlugin


class StubSearch:
    def __init__(self, result=None, exception=None):
        self.result = result
        self.exception = exception
        self.calls = 0

    def search(self, query):
        self.calls += 1
        if self.exception:
            raise self.exception
        return self.result


class StubClient(AIClient):
    def ask(self, prompt, context):
        return normalize_response({"text": "回答", "emotion": "idle"}, "chat")


class NetworkPluginTests(unittest.TestCase):
    def test_should_handle_recognizes_network_intent(self):
        plugin = NetworkPlugin({"enabled": True}, StubSearch())
        for message in ("帮我查一下北京天气", "搜索官方文档", "现在几点", "有什么最新消息"):
            self.assertTrue(plugin.should_handle(message), message)

    def test_normal_chat_does_not_trigger_network(self):
        search = StubSearch()
        plugin = NetworkPlugin({"enabled": True}, search)
        router = AIRouter(StubClient(), StubClient(), plugin)
        result = router.ask("今天心情怎么样", [])
        self.assertEqual(search.calls, 0)
        self.assertEqual(result["source"], "chat")

    def test_disabled_network_never_searches(self):
        search = StubSearch()
        plugin = NetworkPlugin({"enabled": False}, search)
        router = AIRouter(StubClient(), StubClient(), plugin)
        router.ask("查一下天气", [])
        self.assertEqual(search.calls, 0)

    def test_network_exception_becomes_safe_response(self):
        search = StubSearch(exception=RuntimeError("offline"))
        plugin = NetworkPlugin({"enabled": True}, search)
        router = AIRouter(StubClient(), StubClient(), plugin)
        result = router.ask("联网看看天气", [])
        self.assertEqual(result["source"], "tool+llm")
        self.assertEqual(result["emotion"], "sad")
        self.assertEqual(result["text"], "不确定，需要查询。")

    def test_network_ai_response_keeps_five_field_contract(self):
        search = StubSearch({
            "ok": True, "type": "search", "title": "天气",
            "summary": "晴，25 度", "sources": [], "error": "",
        })
        plugin = NetworkPlugin({"enabled": True}, search)
        router = AIRouter(StubClient(), StubClient(), plugin)
        result = router.ask("查一下天气", [])
        self.assertEqual(set(result), {"text", "emotion", "action", "state", "source"})
        self.assertEqual(result["source"], "tool+llm")


if __name__ == "__main__":
    unittest.main()
