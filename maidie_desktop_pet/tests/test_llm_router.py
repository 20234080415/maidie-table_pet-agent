from __future__ import annotations

import unittest

from core.brain.llm_router import LLMIntentRouter


class StubClient:
    def route_intent(self, prompt, context):
        return {"intent": "chat", "task_type": "none", "needs_tools": False,
                "entities": {}, "confidence": 0.9, "reason": "casual conversation"}


class StructuredClient:
    def route_intent(self, prompt, context):
        return {"intent": "task", "task_type": "calculation", "needs_tools": True,
                "entities": {"query": "12 * 8"}, "confidence": 0.82,
                "reason": "calculation requested"}


class LLMRouterScenarioTests(unittest.TestCase):
    def setUp(self):
        self.router = LLMIntentRouter(StubClient())

    def assert_route(self, text, intent, task_type="none", needs_tools=False):
        route = self.router.route(text)
        self.assertEqual(route["intent"], intent, text)
        self.assertEqual(route.get("task_type", "none"), task_type, text)
        self.assertEqual(route.get("needs_tools", False), needs_tools, text)
        return route

    def test_ordinary_chat(self):
        for text in ["Maidie 你今天好可爱", "我今天有点累，陪我聊会儿", "你是不是又在偷懒", "我现在不想写代码了"]:
            self.assert_route(text, "chat")

    def test_current_time(self):
        for text in ["现在几点了", "现在的时间是多少", "帮我看看现在几点啦", "今天几号"]:
            self.assert_route(text, "task", "time_now", True)

    def test_time_delta_entities(self):
        cases = [("我5.40下课，现在还有多久下课", "5.40", "下课"),
                 ("到17:40还有多久", "17:40", ""),
                 ("距离晚上八点还有多久", "晚上八点", ""),
                 ("我八点开会，现在还剩多久", "八点", "开会"),
                 ("下午三点考试，还剩多长时间", "下午三点", "考试"),
                 ("我 6:20 要出门，现在还剩多久", "6:20", "出门")]
        for text, target, event in cases:
            route = self.assert_route(text, "task", "time_delta", True)
            self.assertEqual(route["entities"]["target_time_text"], target)
            self.assertEqual(route["entities"]["event"], event)

    def test_weather(self):
        for text, location in [("今天东京天气怎么样", "东京"), ("明天大阪会下雨吗", "大阪")]:
            route = self.assert_route(text, "task", "weather", True)
            self.assertEqual(route["entities"]["location"], location)
        self.assert_route("我现在出门要不要带伞", "task", "weather", True)

    def test_search(self):
        first = self.assert_route("帮我搜一下 Tavily 是干嘛的", "task", "search", True)
        self.assertEqual(first["entities"]["query"], "Tavily 是干嘛的")
        for text in ["查一下今天 AI 有什么新闻", "搜索一下 PyQt6 托盘图标怎么设置"]:
            self.assert_route(text, "task", "search", True)

    def test_screen_understanding(self):
        for text in ["你看看我屏幕这个报错是什么意思", "帮我看一下当前窗口里有什么",
                     "这个题怎么写，你看一下屏幕", "你能看到我现在打开的软件吗"]:
            route = self.router.route(text)
            self.assertIn(route["intent"], {"vision", "screen"})
            self.assertEqual(route["task_type"], "screen_understanding")

    def test_code_tasks(self):
        for text in ["这个 Python 报错怎么修", "帮我看看这个 Makefile 为什么不执行",
                     "这个函数怎么重构更好", "帮我解释一下这个 CMakeLists.txt"]:
            self.assert_route(text, "code_task", "code_task")

    def test_explicit_coding_agent_request_bypasses_chat_classification(self):
        for text in [
            "你调用open'co'de看看我分析一下我的这个项目",
            "使用 OpenCode 检查当前项目",
            "分析一下我的这个项目",
        ]:
            route = self.assert_route(text, "code_task", "code_task", True)
            self.assertEqual(route["route_source"], "fast_rule")

    def test_time_delta_negative_examples(self):
        for text in ["我快下课了好开心", "今天时间过得好慢", "我不想上课了",
                     "晚上八点这个说法听起来好怪", "5.40 这个数字是什么意思"]:
            self.assertNotEqual(self.router.route(text).get("task_type"), "time_delta", text)

    def test_llm_structured_fields_are_preserved_and_completed(self):
        route = LLMIntentRouter(StructuredClient()).route("帮我算一下 12 * 8")
        self.assertEqual(route["task_type"], "calculation")
        self.assertTrue(route["needs_tools"])
        self.assertEqual(route["entities"]["query"], "12 * 8")
        self.assertEqual(set(route["entities"]), set(LLMIntentRouter.ENTITY_KEYS))

    def test_session_context_is_reused_without_external_history(self):
        self.router.route("我5.40下课")
        route = self.router.route("还有多久下课")
        self.assertEqual(route["task_type"], "time_delta")
        self.assertEqual(route["entities"]["target_time_text"], "5.40")

    def test_invalid_llm_json_keeps_legacy_fallback(self):
        class BrokenClient:
            def route_intent(self, prompt, context): return "not json"
        route = LLMIntentRouter(BrokenClient()).route("今天心情不错")
        self.assertEqual(route["intent"], "chat")
        self.assertEqual(route["task_type"], "none")
        self.assertFalse(route["needs_tools"])
        self.assertEqual(route["route_source"], "fallback")


if __name__ == "__main__":
    unittest.main()
