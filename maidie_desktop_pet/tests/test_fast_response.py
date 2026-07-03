from __future__ import annotations

import json
import os
import unittest
from unittest.mock import Mock

import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.brain import BrainPlanner, LLMIntentRouter, Synthesizer
from core.pet import PetController
from core.session import AISessionCoordinator
from core.tools import WeatherTool


class _Clock:
    def __init__(self): self.value = 0.0
    def __call__(self): return self.value


class _Response:
    def raise_for_status(self): pass
    def json(self):
        return {"current": {"temperature_2m": 23, "wind_speed_10m": 4,
                            "weather_code": 1}}


class _Memory:
    def get_recent(self): return []
    def prompt_context(self): return ""
    def save(self, *_args): pass


class _Future:
    def __init__(self, value=None, done=False): self.value, self.complete = value, done
    def done(self): return self.complete
    def result(self): return self.value


class _Executor:
    def __init__(self, future=None): self.future, self.calls = future or _Future(), []
    def submit(self, function, *args):
        self.calls.append((function, args))
        return self.future
    def shutdown(self, **_kwargs): pass


class _ImmediateExecutor:
    def submit(self, function, *args):
        return _Future(function(*args), done=True)


class FastResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_time_fast_route_skips_llm(self):
        client = Mock()
        client.route_intent.side_effect = AssertionError("LLM route called")
        route = LLMIntentRouter(client).route("现在几点")
        self.assertEqual((route["intent"], route["route_source"]), ("task", "fast_rule"))
        client.route_intent.assert_not_called()

    def test_weather_fast_route_skips_llm(self):
        client = Mock()
        route = LLMIntentRouter(client).route("今天天气怎么样")
        self.assertEqual((route["intent"], route["route_source"]), ("task", "fast_rule"))
        client.route_intent.assert_not_called()

    def test_fast_route_vocabulary_produces_matching_tool_steps(self):
        planner = BrainPlanner()
        self.assertEqual(planner.plan("今天几号")["steps"][0]["tool"], "time")
        self.assertEqual(planner.plan("现在多少度")["steps"][0]["tool"], "weather")
        self.assertEqual(planner.plan("今天冷不冷")["steps"][0]["tool"], "weather")

    def test_simple_technical_explanation_fast_route(self):
        client = Mock()
        route = LLMIntentRouter(client).route("CMake add_library 是什么意思")
        self.assertEqual((route["intent"], route["route_source"]),
                         ("code_task", "fast_rule"))
        client.route_intent.assert_not_called()

    def test_simple_weather_uses_local_response(self):
        client = Mock()
        synthesizer = Synthesizer(client)
        result = synthesizer.synthesize("今天天气怎么样", "tool", {}, [{
            "tool": "weather", "ok": True, "data": {
                "type": "weather", "raw": {"city": "长沙", "temperature": 23,
                                              "forecast": "sunny"}, "source": "api"},
        }], "", [])
        self.assertIn("23", result["text"])
        client.ask.assert_not_called()

    def test_complex_weather_may_use_llm(self):
        client = Mock()
        client.ask.return_value = {"text": "建议", "emotion": "idle",
                                   "action": "talk", "state": "talking"}
        synthesizer = Synthesizer(client)
        synthesizer.synthesize("根据天气给我建议", "tool", {}, [{
            "tool": "weather", "ok": True, "data": {
                "type": "weather", "raw": {"temperature": 23}, "source": "api"},
        }], "", [])
        client.ask.assert_called_once()

    def test_weather_cache_and_expiry(self):
        clock, get = _Clock(), Mock(return_value=_Response())
        tool = WeatherTool(clock=clock, http_get=get)
        first = tool.run("长沙天气")
        clock.value = 30
        second = tool.run("长沙天气")
        clock.value = 601
        third = tool.run("长沙天气")
        self.assertFalse(first["raw"]["cache_hit"])
        self.assertTrue(second["raw"]["cache_hit"])
        self.assertFalse(third["raw"]["cache_hit"])
        self.assertEqual(get.call_count, 2)

    def test_weather_timeout_is_structured(self):
        tool = WeatherTool(http_get=Mock(side_effect=requests.Timeout("slow")))
        result = tool.run("今天天气")
        self.assertEqual(result["raw"]["error_code"], "weather_timeout")
        self.assertFalse(result["raw"]["cache_hit"])

    def test_memory_skip_rules(self):
        self.assertFalse(PetController._should_extract_memory("现在几点", {"source": "tool"}))
        self.assertFalse(PetController._should_extract_memory("今天天气怎么样", {"source": "tool"}))
        self.assertTrue(PetController._should_extract_memory("我喜欢简洁的回答", {"source": "chat"}))

    def test_background_executors_are_separate(self):
        controller = PetController(Mock(), _Memory())
        self.assertIsNot(controller.ai_session.executor, controller._proactive_executor)
        self.assertIsNot(controller.ai_session.executor, controller._memory_executor)
        controller.shutdown()

    def test_normal_chat_attention_refresh_does_not_call_ocr(self):
        runtime = Mock()
        runtime.awareness.window_tracker.snapshot.return_value = {}
        runtime.awareness.app_tracker = None
        runtime.awareness.screen_reader._last_result = {}
        controller = PetController(Mock(), _Memory(), proactive_runtime=runtime)

        controller._refresh_attention()

        runtime.awareness.screen_reader.read.assert_not_called()
        controller.shutdown()

    def test_proactive_does_not_occupy_user_executor(self):
        runtime = Mock()
        runtime.engine.enabled = True
        controller = PetController(Mock(), _Memory(), logger=Mock(), proactive_runtime=runtime)
        controller._proactive_timer.stop()
        proactive, user = _Executor(), _Executor()
        controller._proactive_executor.shutdown(wait=False, cancel_futures=True)
        controller._user_executor.shutdown(wait=False, cancel_futures=True)
        controller._proactive_executor = proactive
        controller._user_executor = user
        controller.ai_session.executor = user
        controller._proactive_tick()
        controller.submit_text("hello")
        self.assertEqual(len(proactive.calls), 1)
        self.assertEqual(len(user.calls), 1)
        controller.shutdown()

    def test_performance_log_has_all_stage_fields(self):
        logger = Mock()
        router = Mock()
        router.ask_stream.return_value = {"text": "ok", "emotion": "idle",
                                          "action": "talk", "state": "talking"}
        session = AISessionCoordinator(router, _ImmediateExecutor(), logger,
                                       lambda *_args: ([], None), Mock(), Mock(), Mock())
        session.submit("hello")
        payload = json.loads(logger.debug.call_args.args[1])
        for field in ("executor_queue_delay_ms", "route_duration_ms", "tool_duration_ms",
                      "synthesize_duration_ms", "total_response_duration_ms"):
            self.assertIn(field, payload)
        session.shutdown()


if __name__ == "__main__":
    unittest.main()
