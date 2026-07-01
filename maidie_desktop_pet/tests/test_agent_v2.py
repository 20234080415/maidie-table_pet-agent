from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from core.awareness import IdleDetector, MouseTracker, WindowTracker
from core.awareness.context import AwarenessContext
from core.proactive import ProactiveEngine
from core.tasks import TaskScheduler


class Clock:
    def __init__(self, value: float = 0.0): self.value = value
    def __call__(self): return self.value


class AgentV2Tests(unittest.TestCase):
    def test_awareness_idle_detection(self):
        clock = Clock()
        idle = IdleDetector(10, clock)
        mouse = MouseTracker(idle, clock=clock)
        mouse.record(0, 0)
        clock.value = 3
        mouse.record(30, 0)
        self.assertEqual(mouse.state, "slow_move")
        clock.value = 14
        self.assertEqual(mouse.state, "idle")
        snapshot = AwarenessContext(mouse, WindowTracker(lambda: "Visual Studio Code")).snapshot()
        self.assertEqual(set(snapshot), {"mouse_state", "window_state", "idle_time"})

    def test_window_tracking(self):
        tracker = WindowTracker()
        self.assertEqual(tracker.state("project - Visual Studio Code"), "coding")
        self.assertEqual(tracker.state("Docs - Google Chrome"), "browser")
        self.assertEqual(tracker.state("Discord"), "chat")
        self.assertEqual(tracker.state("Desktop"), "unknown")

    def test_proactive_trigger(self):
        clock = Clock(500)
        engine = ProactiveEngine(True, cooldown_seconds=30, idle_trigger_seconds=300,
                                 random_chance=0, clock=clock)
        decision = engine.decide({"idle_time": 301, "window_state": "unknown"})
        self.assertIsNotNone(decision)
        self.assertEqual(decision.kind, "care")

    def test_task_scheduler(self):
        now = datetime(2026, 7, 3, 9, 0)
        scheduler = TaskScheduler(now=lambda: now)
        once = scheduler.add({"id": "task_001", "type": "once",
                              "trigger": (now - timedelta(minutes=1)).isoformat(),
                              "action": "提醒喝水", "enabled": True})
        cron = scheduler.add({"id": "task_002", "type": "cron",
                              "trigger": "daily@09:00", "action": "早安", "enabled": True})
        self.assertEqual({task.id for task in scheduler.tick()}, {once.id, cron.id})
        self.assertEqual(scheduler.tick(), [])

    def test_condition_task(self):
        now = datetime(2026, 7, 1, 12, 0)
        scheduler = TaskScheduler(now=lambda: now, condition_cooldown=60)
        scheduler.add({"id": "task_idle", "type": "condition",
                       "trigger": {"idle_seconds": 7200}, "action": "起来活动", "enabled": True})
        self.assertEqual(scheduler.tick({"idle_time": 7199}), [])
        self.assertEqual([task.id for task in scheduler.tick({"idle_time": 7200})], ["task_idle"])

    def test_no_spam_behavior(self):
        clock = Clock(500)
        engine = ProactiveEngine(True, cooldown_seconds=300, idle_trigger_seconds=10,
                                 random_chance=1, clock=clock)
        self.assertIsNotNone(engine.decide({"idle_time": 20}))
        clock.value = 501
        self.assertIsNone(engine.decide({"idle_time": 20}))
        clock.value = 801
        self.assertIsNotNone(engine.decide({"idle_time": 20}))

    def test_proactive_is_disabled_by_default(self):
        self.assertFalse(ProactiveEngine().should_trigger({"idle_time": 99999}))


if __name__ == "__main__":
    unittest.main()
