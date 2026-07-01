from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QPoint

from core.actions import ActionRegistry
from core.pet import PetController
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

    def test_drag_gestures_are_data_driven(self):
        self.assertEqual(self.registry.match_gesture("drag-right"), "dizzy-right")
        self.assertEqual(self.registry.match_gesture("drag-left"), "dizzy-left")


class DragActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.registry = ActionRegistry(ROOT / "assets" / "actions" / "actions.json")
        self.controller = PetController(None, None, action_registry=self.registry)

    def tearDown(self):
        self.controller.shutdown()

    def drag(self, dx: float) -> None:
        self.controller.on_pet_dragged(100, 100, 160, 190, dx)

    def test_right_drag_triggers_dizzy_right(self):
        with patch.object(self.controller, "_play_action", return_value=True) as play:
            self.drag(31)
        play.assert_called_once_with("dizzy-right", force=True)

    def test_left_drag_triggers_dizzy_left(self):
        with patch.object(self.controller, "_play_action", return_value=True) as play:
            self.drag(-31)
        play.assert_called_once_with("dizzy-left", force=True)

    def test_short_drag_does_not_trigger_dizzy_action(self):
        with patch.object(self.controller, "_play_action") as play:
            self.drag(30)
        play.assert_not_called()

    def test_action_cooldown_is_safe(self):
        with patch("core.pet.QTimer.singleShot"):
            self.assertTrue(self.controller._play_action("dizzy-right", force=True))
            self.assertFalse(self.controller._play_action("dizzy-right", force=True))
            self.drag(31)


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
