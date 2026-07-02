from __future__ import annotations

import logging
import unittest

from core.brain.planner import BrainPlanner
from core.brain.search_query import SearchQueryResolver
from core.tools.search_tool import SearchTool
from network.search import SearchService


class Memory:
    def __init__(self):
        self.last_search_query = ""

    def set_last_search_query(self, query):
        self.last_search_query = query

    def get_last_search_query(self):
        return self.last_search_query


class CountingNetwork:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"ok": True, "summary": "ok", "sources": []}

    def handle(self, query):
        self.calls.append(query)
        return dict(self.result)


class SearchContextTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.resolver = SearchQueryResolver()

    def test_extracts_explicit_search_query(self):
        result = self.resolver.resolve("搜索一下 DeepSeek 最新价格", self.memory)
        self.assertEqual(result.query, "DeepSeek 最新价格")
        self.assertEqual(result.source, "explicit_user_text")

    def test_extracts_date_search_query(self):
        result = self.resolver.resolve("去给我搜索一下6.30号发生了什么事情", self.memory)
        self.assertEqual(result.query, "6.30号发生了什么事情")

    def test_extracts_bare_lookup_verb(self):
        result = self.resolver.resolve("帮我查PyQt6 新版本", self.memory)
        self.assertEqual(result.query, "PyQt6 新版本")

    def test_ellipsis_uses_last_search_query(self):
        self.memory.set_last_search_query("Maidie")
        result = self.resolver.resolve("帮我搜一下", self.memory)
        self.assertEqual((result.query, result.source), ("Maidie", "last_search_query"))

    def test_missing_context_does_not_plan_tavily_call(self):
        plan = BrainPlanner().plan("帮我搜一下", self.memory)
        self.assertEqual(plan["steps"], [])
        self.assertTrue(plan["missing_search_query"])

    def test_clipboard_is_an_explicit_internal_source(self):
        result = self.resolver.resolve("搜剪贴板里的内容", self.memory, "copied words")
        self.assertEqual((result.query, result.source), ("copied words", "clipboard"))
        # Clipboard text is context, not a fabricated user chat message.
        self.assertFalse(hasattr(self.memory, "chat_history"))

    def test_empty_results_are_classified_and_logged(self):
        network = CountingNetwork({"ok": False, "error": "none", "sources": [],
                                   "failure_reason": "EMPTY_RESULTS"})
        with self.assertLogs("core.tools.search_tool", logging.INFO) as logs:
            raw = SearchTool(network).run("query", raw_user_text="搜query")["raw"]
        self.assertEqual(raw["failure_reason"], "EMPTY_RESULTS")
        self.assertIn("failure_reason=EMPTY_RESULTS", " ".join(logs.output))

    def test_missing_tavily_key_is_classified(self):
        result = SearchService(api_key="").search("Maidie")
        self.assertEqual(result["failure_reason"], "API_KEY_MISSING")


if __name__ == "__main__":
    unittest.main()
