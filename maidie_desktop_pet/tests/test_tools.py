"""Compatibility tests for the deprecated AIRouter; production uses core.brain."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from ai.client import AIClient, normalize_response
from ai.router import AIRouter
from core.plugins.network import NetworkPlugin
from core.tools import TimeTool, ToolRegistry, WeatherTool


class CountingClient(AIClient):
    def __init__(self):
        self.calls = 0

    def ask(self, prompt, context):
        self.calls += 1
        return normalize_response({"text": "LLM"}, "chat")


class CountingSearch:
    def __init__(self):
        self.calls = 0

    def search(self, query):
        self.calls += 1
        return {
            "ok": True, "type": "search", "title": "result",
            "summary": "search result", "sources": [], "error": "",
        }


class ToolSystemTests(unittest.TestCase):
    def test_time_tool(self):
        tool = TimeTool()
        self.assertTrue(tool.match("现在几点？"))
        result = tool.run("现在几点？")
        self.assertEqual(result["type"], "time")
        self.assertEqual(result["source"], "local")
        self.assertNotIn("text", result)
        self.assertIn("iso", result["raw"])

    @patch("core.tools.weather_tool.requests.get")
    def test_weather_tool(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "current": {
                "temperature_2m": 29.5,
                "wind_speed_10m": 8.2,
                "weather_code": 1,
            }
        }
        get.return_value = response
        result = WeatherTool().run("长沙天气")
        self.assertEqual(result["type"], "weather")
        self.assertEqual(result["source"], "api")
        self.assertNotIn("text", result)
        self.assertEqual(result["raw"]["temperature"], 29.5)
        self.assertEqual(result["raw"]["wind"], 8.2)
        self.assertEqual(get.call_args.kwargs["timeout"], 5)

    def test_registry_match(self):
        registry = ToolRegistry([TimeTool(), WeatherTool()])
        self.assertEqual(registry.match("today 是几号").name, "time")
        self.assertEqual(registry.match("长沙天气").name, "weather")
        self.assertIsNone(registry.run("陪我聊聊天"))

    def test_router_tool_priority(self):
        client = CountingClient()
        search = CountingSearch()
        network = NetworkPlugin({"enabled": True}, search)
        router = AIRouter(
            client,
            client,
            network_plugin=network,
            tool_registry=ToolRegistry([TimeTool(), WeatherTool()]),
        )
        result = router.ask("现在几点？请查一下", [])
        self.assertEqual(result["source"], "tool+llm")
        self.assertEqual(client.calls, 0)
        self.assertEqual(search.calls, 0)
        self.assertEqual(
            set(result), {"text", "emotion", "action", "state", "source"}
        )


if __name__ == "__main__":
    unittest.main()
