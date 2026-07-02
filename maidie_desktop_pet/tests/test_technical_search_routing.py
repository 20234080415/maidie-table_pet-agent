from __future__ import annotations

import unittest

from core.brain.planner import BrainPlanner


class TechnicalSearchRoutingTests(unittest.TestCase):
    def test_cmake_function_list_uses_search(self):
        plan = BrainPlanner().plan_for_intent(
            "帮我查找一下CMakeLists里面有哪些函数", "code_task"
        )
        self.assertEqual(plan["steps"][0]["tool"], "search")
        self.assertIn("official documentation", plan["steps"][0]["params"]["query"])

    def test_cmake_function_meaning_uses_search(self):
        plan = BrainPlanner().plan_for_intent(
            "add_library()是什么意思", "code_task"
        )
        self.assertEqual(plan["steps"][0]["tool"], "search")

    def test_debugging_remains_a_code_task(self):
        plan = BrainPlanner().plan_for_intent("帮我修复这个编译错误", "code_task")
        self.assertEqual(plan["steps"][0]["tool"], "codex")


if __name__ == "__main__":
    unittest.main()
