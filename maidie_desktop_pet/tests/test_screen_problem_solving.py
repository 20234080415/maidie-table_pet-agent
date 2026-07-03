from __future__ import annotations

import unittest
from unittest.mock import Mock

from core.brain import BrainExecutor, BrainPlanner, BrainRouter, ProblemAnalyzer, Synthesizer
from core.tools import ToolRegistry
from core.tools.base import Tool


class _ResultTool(Tool):
    def __init__(self, name, result):
        self.name = name
        self.result = result
        self.calls = []

    def match(self, _query):
        return False

    def run(self, query, **_kwargs):
        self.calls.append(query)
        return self.result


class _OfflineClient:
    api_key = ""


class _Memory:
    def prompt_context(self):
        return ""


class ScreenProblemSolvingTests(unittest.TestCase):
    def test_python_error_generates_search_query(self):
        problem = ProblemAnalyzer().analyze({
            "visible_text": "Traceback (most recent call last):\nValueError: invalid literal for int()",
            "screen_summary": "Python terminal in VSCode",
            "task_type": "code_error", "confidence": 0.92,
        })

        self.assertEqual(problem.problem_type, "code_error")
        self.assertEqual(problem.error_message, "ValueError: invalid literal for int()")
        self.assertTrue(problem.needs_search)
        self.assertIn("ValueError", problem.search_query)
        self.assertIn("Python", problem.search_query)

    def test_question_text_is_extracted(self):
        problem = ProblemAnalyzer().analyze({
            "visible_text": "题目：请问函数 f(x)=x² 的最小值是多少？",
            "task_type": "math_problem", "confidence": 0.9,
        })

        self.assertEqual(problem.problem_type, "question")
        self.assertIn("最小值", problem.question_text)

    def test_low_confidence_does_not_search(self):
        problem = ProblemAnalyzer().analyze({
            "visible_text": "ValueError: maybe blurred", "task_type": "code_error",
            "confidence": 0.3,
        })
        screen = _ResultTool("screen", {"type": "screen", "source": "qwen_vl", "raw": {
            "problem_context": problem.to_dict(),
        }})
        search = _ResultTool("search", {"type": "search", "source": "api", "raw": {}})
        executor = BrainExecutor(ToolRegistry([screen, search]))

        executions = executor.execute(BrainPlanner.screen_plan("看看报错"), "看看报错")

        self.assertEqual([item["tool"] for item in executions], ["screen"])
        self.assertEqual(search.calls, [])

    def test_planner_and_executor_run_screen_then_search(self):
        plan = BrainPlanner.screen_plan("你看看屏幕这个报错怎么修")
        self.assertEqual([step["tool"] for step in plan["steps"]], ["screen", "search"])
        screen = _ResultTool("screen", {"type": "screen", "source": "qwen_vl", "raw": {
            "problem_context": {"needs_search": True, "search_query": "Python TypeError fix"},
        }})
        search = _ResultTool("search", {"type": "search", "source": "tavily", "raw": {
            "summary": "Check the argument type",
        }})

        executions = BrainExecutor(ToolRegistry([screen, search])).execute(plan, plan["goal"])

        self.assertEqual([item["tool"] for item in executions], ["screen", "search"])
        self.assertEqual(search.calls, ["Python TypeError fix"])

    def test_planner_can_optionally_add_memory(self):
        plan = BrainPlanner.screen_plan("看看这个报错，结合上次的情况回答")

        self.assertEqual([step["tool"] for step in plan["steps"]],
                         ["screen", "search", "memory"])

    def test_search_failure_keeps_screen_facts_in_fallback(self):
        tool_data = [
            {"tool": "screen", "ok": True, "data": {"type": "screen", "source": "qwen_vl",
             "raw": {"problem_context": {"error_message": "TypeError: bad operand",
                                             "visible_text": "TypeError: bad operand"}}}},
            {"tool": "search", "ok": False, "data": {"type": "search", "source": "tavily",
             "raw": {"error": "offline", "failure_reason": "NETWORK_ERROR"}}},
        ]

        result = Synthesizer(_OfflineClient()).synthesize(
            "这个报错怎么修", "screen", {}, tool_data, "", [], technical=True,
        )

        self.assertIn("TypeError: bad operand", result["text"])
        self.assertIn("搜索", result["text"])

    def test_normal_chat_never_reads_screen(self):
        client = Mock()
        client.route_intent.return_value = {"intent": "chat", "confidence": 1.0}
        client.ask.return_value = {"text": "你好", "emotion": "idle", "action": "talk",
                                   "state": "talking"}
        screen = _ResultTool("screen", {"type": "screen", "source": "local", "raw": {}})
        router = BrainRouter(client, client, ToolRegistry([screen]), _Memory())

        router.route("你好，今天心情不错", [])

        self.assertEqual(screen.calls, [])


if __name__ == "__main__":
    unittest.main()
