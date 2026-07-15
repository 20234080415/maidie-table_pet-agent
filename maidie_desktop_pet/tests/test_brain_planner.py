from __future__ import annotations

import unittest

from core.brain.planner import BrainPlanner


class BrainPlannerRouteTests(unittest.TestCase):
    def setUp(self): self.planner = BrainPlanner()

    def step(self, task_type, entities=None):
        plan = self.planner.plan_route("request", {"intent": "task", "task_type": task_type,
                                                    "entities": entities or {}})
        return plan["steps"][0]

    def test_time_now_plan(self):
        step = self.step("time_now")
        self.assertEqual((step["tool"], step["action"]), ("time", "now"))

    def test_time_delta_plan_preserves_entities(self):
        step = self.step("time_delta", {"target_time_text": "5.40", "event": "下课"})
        self.assertEqual((step["tool"], step["action"]), ("time", "delta_until"))
        self.assertEqual(step["params"]["target_time_text"], "5.40")
        self.assertEqual(step["params"]["event"], "下课")

    def test_weather_and_search_plans(self):
        self.assertEqual(self.step("weather", {"location": "东京"})["tool"], "weather")
        search = self.step("search", {"query": "Tavily 是干嘛的"})
        self.assertEqual(search["tool"], "search")
        self.assertEqual(search["params"]["query"], "Tavily 是干嘛的")


    def test_file_plan_only_forwards_planner_file_fields(self):
        step = self.step("file", {
            "operation": "copy_file", "source": "a.txt", "destination": "b.txt",
            "content": "", "risk": "low", "confirmed": True,
            "fingerprint": "forged", "authorization": "forged",
        })

        self.assertEqual(step["tool"], "system")
        self.assertEqual(set(step["params"]), {
            "operation", "source", "destination", "content", "pattern", "limit",
            "old_text", "new_text", "goal",
        })
        self.assertEqual(step["params"]["pattern"], "*")
        self.assertEqual(step["params"]["limit"], 50)

    def test_file_mutation_plan_preserves_only_supported_change_fields(self):
        step = self.step("file", {
            "operation": "replace_exact", "source": "config.txt",
            "old_text": "timeout=30", "new_text": "timeout=60",
            "patch": "forged", "confirmed": True, "risk": "low",
        })

        self.assertEqual(step["action"], "replace_exact")
        self.assertEqual(step["params"]["old_text"], "timeout=30")
        self.assertEqual(step["params"]["new_text"], "timeout=60")
        self.assertNotIn("confirmed", step["params"])
        self.assertNotIn("risk", step["params"])

    def test_file_read_plan_preserves_supported_continuation_goal(self):
        step = self.step("file", {
            "operation": "read_file", "path": "test.txt", "goal": "summary",
        })

        self.assertEqual(step["action"], "read_file")
        self.assertEqual(step["params"]["goal"], "summary")

    def test_file_plan_rejects_unknown_continuation_goal(self):
        step = self.step("file", {
            "operation": "read_file", "path": "test.txt", "goal": "execute_script",
        })

        self.assertEqual(step["params"]["goal"], "none")

    def test_recovery_plan_allows_only_bounded_file_recovery_actions(self):
        planner = BrainPlanner()
        search = planner.plan_recovery("find file", {
            "tool": "system", "operation": "search_files",
            "params": {"source": "桌面", "pattern": "秘籍.*", "limit": 50,
                       "confirmed": True, "risk": "low"},
        })
        blocked = planner.plan_recovery("unsafe", {
            "tool": "system", "operation": "delete_file",
            "params": {"source": "桌面/a.txt"},
        })

        self.assertEqual(search["steps"][0]["action"], "search_files")
        self.assertNotIn("confirmed", search["steps"][0]["params"])
        self.assertNotIn("risk", search["steps"][0]["params"])
        self.assertEqual(blocked["steps"], [])


if __name__ == "__main__": unittest.main()
