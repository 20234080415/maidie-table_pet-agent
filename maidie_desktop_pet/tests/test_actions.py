from __future__ import annotations

import unittest
from pathlib import Path

from PyQt6.QtCore import QPoint

from core.actions import ActionRegistry
from input.gesture import PetGestureRecognizer


ROOT = Path(__file__).resolve().parents[1]


class ActionRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ActionRegistry(ROOT / "assets" / "actions" / "actions.json")

    def test_message_triggers_are_data_driven(self):
        self.assertEqual(self.registry.match_message("you are very cute"), "shy")
        self.assertEqual(self.registry.match_message("thank you, success"), "celebrate")

    def test_cooldown_blocks_immediate_repeat(self):
        self.assertTrue(self.registry.can_trigger("headpat"))
        self.registry.mark_triggered("headpat")
        self.assertFalse(self.registry.can_trigger("headpat"))


class GestureTests(unittest.TestCase):
    def test_horizontal_reversal_is_headpat(self):
        gesture = PetGestureRecognizer()
        gesture.begin("head", QPoint(50, 20), 160)
        self.assertEqual(gesture.update(QPoint(68, 21)), "pending")
        self.assertEqual(gesture.update(QPoint(45, 20)), "headpat")

    def test_vertical_motion_remains_drag(self):
        gesture = PetGestureRecognizer()
        gesture.begin("head", QPoint(50, 20), 160)
        self.assertEqual(gesture.update(QPoint(52, 45)), "drag")

    def test_body_motion_remains_drag(self):
        gesture = PetGestureRecognizer()
        gesture.begin("body", QPoint(50, 100), 160)
        self.assertEqual(gesture.update(QPoint(54, 102)), "drag")


if __name__ == "__main__":
    unittest.main()
