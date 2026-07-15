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
        self.assertEqual(set(step["params"]), {"operation", "source", "destination", "content"})


if __name__ == "__main__": unittest.main()
