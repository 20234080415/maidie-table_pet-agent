from __future__ import annotations

import unittest

from ai.client import AIClient, OpenAICompatibleClient, normalize_response
from ai.router import AIRouter
from core.movement import Bounds, MovementController, Vec2
from core.state import BehaviorPriority, PetState, StateMachine


class StubClient(AIClient):
    def __init__(self, source: str):
        self.source = source

    def ask(self, prompt, context):
        return normalize_response({"text": prompt, "emotion": "idle"}, self.source)


class StateMachineTests(unittest.TestCase):
    def test_priority_lock_rejects_equal_and_lower_priority(self):
        machine = StateMachine()
        self.assertTrue(machine.transition(PetState.REACTING, BehaviorPriority.CURSOR_INTERACTION, 1000))
        self.assertFalse(machine.transition(PetState.TALKING, BehaviorPriority.AI_TALKING))
        self.assertFalse(machine.transition(PetState.IDLE, BehaviorPriority.CURSOR_INTERACTION))
        self.assertTrue(machine.transition(PetState.REACTING, BehaviorPriority.USER_CLICK))


class MovementTests(unittest.TestCase):
    def test_velocity_drives_idle_walk_run(self):
        motion = MovementController(walk_threshold=4, run_threshold=50, acceleration=500)
        self.assertEqual(motion.classify_state(), PetState.IDLE)
        motion.move_to(Vec2(800, 0), run=True)
        motion.tick(0.02, Bounds(0, 0, 1920, 1080))
        self.assertEqual(motion.classify_state(), PetState.WALK)
        for _ in range(8):
            motion.tick(0.05, Bounds(0, 0, 1920, 1080))
        self.assertEqual(motion.classify_state(), PetState.RUN)
        motion.stop()
        self.assertEqual(motion.classify_state(), PetState.IDLE)

    def test_screen_edges_are_never_crossed(self):
        motion = MovementController()
        motion.sync_geometry(0, 0, 320, 380)
        motion.move_to(Vec2(5000, 5000), run=True)
        bounds = Bounds(0, 0, 1280, 720)
        for _ in range(300):
            motion.tick(0.05, bounds)
        self.assertLessEqual(motion.position.x, 960)
        self.assertLessEqual(motion.position.y, 340)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.router = AIRouter(StubClient("chat"), StubClient("codex"))

    def test_routes_technical_intent(self):
        self.assertEqual(self.router.classify("帮我调试 Python 报错"), "codex")
        self.assertEqual(self.router.classify("今天心情怎么样"), "chat")

    def test_every_response_has_contract_fields(self):
        result = self.router.ask("hello", [])
        self.assertEqual(set(result), {"text", "emotion", "action", "state", "source"})

    def test_missing_key_points_user_to_settings(self):
        client = OpenAICompatibleClient("", "https://api.deepseek.com", "test")
        result = client.ask("hello", [])
        self.assertIn("右键", result["text"])
        self.assertIn("设置", result["text"])


if __name__ == "__main__":
    unittest.main()
