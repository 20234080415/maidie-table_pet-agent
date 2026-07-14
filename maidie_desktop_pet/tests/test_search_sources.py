from __future__ import annotations

import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.brain import BrainExecutor, Synthesizer
from core.session import AISessionCoordinator
from core.tools import SearchTool, ToolRegistry
from network.search import SearchService
from ui.long_response_panel import LongResponsePanel


class _SearchClient:
    def __init__(self, payload):
        self.payload = payload

    def post_json(self, _url, _payload):
        return self.payload, None


class _NetworkPlugin:
    def __init__(self, result, show_sources=True):
        self.result = result
        self.show_sources = show_sources

    def handle(self, _query):
        return dict(self.result)


class _ModelClient:
    api_key = "configured"

    def ask(self, _prompt, _context):
        return {
            "text": "Structured answer with https://model.invalid/fake",
            "emotion": "idle",
            "action": "talk",
            "state": "talking",
        }


class _Executor:
    def submit(self, *_args):
        return Mock()


def _search_result(sources):
    return {
        "ok": True,
        "type": "search",
        "title": "Search result",
        "summary": "Structured search facts",
        "sources": sources,
        "error": "",
        "failure_reason": "",
        "result_count": len(sources),
    }


class SearchSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_search_service_normalizes_deduplicates_and_limits_sources(self):
        items = [
            {"title": "One <b>", "url": "https://Example.com/a#part", "content": "one"},
            {"title": "Duplicate", "url": "https://example.com/a", "content": "dup"},
            {"title": "Unsafe", "url": "javascript:alert(1)", "content": "unsafe"},
            {"title": "FTP", "url": "ftp://example.com/file", "content": "ftp"},
        ]
        items.extend(
            {"title": f"Item {index}", "url": f"https://site{index}.test/page"}
            for index in range(2, 8)
        )
        service = SearchService(api_key="key")
        service.client = _SearchClient({"answer": "answer", "results": items})

        result = service.search("query")

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["sources"]), 5)
        self.assertEqual(result["sources"][0], {
            "title": "One <b>",
            "url": "https://Example.com/a",
            "domain": "example.com",
        })
        self.assertEqual(len({source["url"].lower() for source in result["sources"]}), 5)
        self.assertTrue(all(source["url"].startswith(("http://", "https://"))
                            for source in result["sources"]))
        self.assertTrue(all(source["domain"] for source in result["sources"]))

    def test_synthesizer_copies_tool_sources_and_ignores_model_urls(self):
        sources = [{
            "title": "Trusted",
            "url": "https://trusted.example/doc",
            "domain": "trusted.example",
        }]
        executions = self._execute_search(sources, show_sources=False)

        result = Synthesizer(_ModelClient()).synthesize(
            "search this", "tool", {"steps": []}, executions, "", []
        )

        self.assertEqual(result["sources"], sources)
        self.assertFalse(result["show_sources"])
        self.assertNotIn("https://model.invalid/fake", [s["url"] for s in result["sources"]])

    def test_session_preserves_source_metadata(self):
        session = self._make_session()
        sources = [{"title": "Docs", "url": "https://docs.example/", "domain": "docs.example"}]

        session.handle_result({
            "text": "answer", "source": "tool", "sources": sources, "show_sources": True,
        })

        self.assertEqual(session.pending_response["sources"], sources)
        self.assertTrue(session.pending_response["show_sources"])
        session.shutdown()

    def test_panel_visibility_follows_flag_and_nonempty_sources(self):
        sources = [{"title": "Docs", "url": "https://docs.example/a", "domain": "docs.example"}]
        panel = LongResponsePanel()

        panel.show_result("Result", full_text="body", sources=sources, show_sources=True)
        html = panel.browser.toHtml()
        self.assertIn("来源", panel.browser.toPlainText())
        self.assertIn('href="https://docs.example/a"', html)

        panel.show_result("Result", full_text="body", sources=sources, show_sources=False)
        self.assertNotIn("来源", panel.browser.toPlainText())
        panel.show_result("Result", full_text="body", sources=[], show_sources=True)
        self.assertNotIn("来源", panel.browser.toPlainText())
        panel.close()

    def test_panel_filters_unsafe_urls_and_escapes_html(self):
        panel = LongResponsePanel()
        panel.show_result(
            "Result",
            full_text="<script>bad()</script>",
            sources=[
                {"title": "<b>Unsafe</b>", "url": "javascript:alert(1)", "domain": "bad"},
                {"title": "<b>Safe</b>", "url": "https://safe.example/?q=<x>",
                 "domain": "safe.example"},
            ],
            show_sources=True,
        )
        html = panel.browser.toHtml().lower()

        self.assertNotIn("javascript:", html)
        self.assertNotIn("<script>bad()", html)
        self.assertNotIn("<b>safe</b>", html)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", html)
        self.assertIn("safe.example", panel.browser.toPlainText())
        panel.close()

    def test_search_pipeline_reaches_session_and_panel(self):
        sources = [{
            "title": "Official docs",
            "url": "https://official.example/docs",
            "domain": "official.example",
        }]
        executions = self._execute_search(sources, show_sources=True)
        synthesized = Synthesizer(_ModelClient()).synthesize(
            "search docs", "tool", {"steps": []}, executions, "", []
        )
        session = self._make_session()
        session.handle_result(synthesized)
        response = session.pending_response
        panel = LongResponsePanel()
        panel.show_result(
            response.get("panel_title", "Result"),
            response.get("content", {}),
            response.get("panel_text", response["text"]),
            sources=response["sources"],
            show_sources=response["show_sources"],
        )

        self.assertEqual(response["sources"], sources)
        self.assertIn('href="https://official.example/docs"', panel.browser.toHtml())
        self.assertNotIn('href="https://model.invalid/fake"', panel.browser.toHtml())
        panel.close()
        session.shutdown()

    @staticmethod
    def _execute_search(sources, show_sources=True):
        plugin = _NetworkPlugin(_search_result(sources), show_sources=show_sources)
        executor = BrainExecutor(ToolRegistry([SearchTool(plugin)]))
        return executor.execute({"steps": [{
            "tool": "search", "params": {"query": "docs"},
        }]}, "search docs")

    @staticmethod
    def _make_session():
        return AISessionCoordinator(
            Mock(), _Executor(), Mock(), lambda _message, _proactive: ([], None),
            Mock(), Mock(), Mock(),
        )


if __name__ == "__main__":
    unittest.main()
