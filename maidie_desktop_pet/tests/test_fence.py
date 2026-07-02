from __future__ import annotations

import os
import unittest
from pathlib import Path
from time import monotonic
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import QApplication

from core.behavior import AutonomousBehaviorController
from core.experience import DialoguePool
from core.fence import FenceController, FenceZone
from core.movement import Bounds, MovementController, Vec2
from core.pet import PetController
from ui.fence_overlay import FenceOverlayWindow
from ui.window import PetWindow


class _Memory:
    def get_recent(self): return []
    def prompt_context(self): return ""
    def save(self, *_args): pass


class FenceZoneTests(unittest.TestCase):
    def test_disabled_fence_does_not_clamp(self):
        fence = FenceZone()
        self.assertEqual(fence.clamp_point(-50, 900, 40, 50), (-50, 900))
        self.assertTrue(fence.contains_pet(-50, 900, 40, 50))

    def test_enabled_fence_clamps_whole_pet(self):
        fence = FenceZone(padding=0)
        fence.enable(Bounds(100, 100, 300, 260))
        self.assertEqual(fence.clamp_point(290, 250, 60, 80), (240, 180))
        self.assertTrue(fence.contains_pet(240, 180, 60, 80))

    def test_contains_checks_pet_width_and_height(self):
        fence = FenceZone(padding=0)
        fence.enable(Bounds(0, 0, 100, 100))
        self.assertFalse(fence.contains_pet(75, 75, 30, 30))
        self.assertTrue(fence.contains_pet(70, 70, 30, 30))

    def test_nearest_inside_position_for_external_drop(self):
        fence = FenceController(padding=0)
        fence.enable(Bounds(10, 20, 210, 220))
        self.assertEqual(fence.nearest_inside_position(-100, 500, 50, 60), (10, 160))

    def test_too_small_fence_safely_expands_effective_bounds(self):
        fence = FenceZone(padding=4)
        fence.enable(Bounds(10, 10, 30, 30))
        bounds = fence.active_bounds(80, 90, Bounds(0, 0, 100, 100))
        self.assertGreaterEqual(bounds.right - bounds.left, 80)
        self.assertGreaterEqual(bounds.bottom - bounds.top, 90)
        x, y = fence.clamp_point(999, 999, 80, 90)
        self.assertTrue(fence.contains_pet(x, y, 80, 90))

    def test_all_edges_are_detected(self):
        fence = FenceZone(padding=0)
        fence.enable(Bounds(0, 0, 100, 100))
        self.assertEqual(fence.hit_test_edge(0, 0, 20, 20), {"left", "top"})
        self.assertEqual(fence.hit_test_edge(80, 80, 20, 20), {"right", "bottom"})

    def test_complaint_cooldown(self):
        fence = FenceZone(complain_cooldown_ms=1000)
        self.assertTrue(fence.should_complain(1000))
        self.assertFalse(fence.should_complain(1500))
        self.assertTrue(fence.should_complain(2000))

    def test_autonomous_targets_stay_inside_fence(self):
        fence = FenceZone(padding=0)
        fence.enable(Bounds(100, 100, 500, 400))
        bounds = fence.active_bounds(80, 90, Bounds(0, 0, 1920, 1080))
        behavior = AutonomousBehaviorController(seed=7)
        targets = []
        for _ in range(30):
            behavior._next_decision = 0
            intent = behavior.decide(bounds, (80, 90), Vec2(999, 999))
            if intent and intent.target:
                targets.append(intent.target)
        self.assertTrue(targets)
        self.assertTrue(all(fence.contains_pet(target.x, target.y, 80, 90)
                            for target in targets))

    def test_movement_tick_clamps_even_without_target(self):
        movement = MovementController()
        movement.sync_geometry(500, 500, 50, 60)
        position = movement.tick(0.016, Bounds(10, 20, 210, 220))
        self.assertEqual(position, Vec2(160, 160))


class DialoguePoolTests(unittest.TestCase):
    def test_event_pools_are_separate_and_populated(self):
        pool = DialoguePool()
        for event in ("fence_enabled", "fence_disabled", "fence_snapback",
                      "fence_edge_complain"):
            self.assertGreaterEqual(len(pool.phrases(event)), 4)
        self.assertNotEqual(pool.phrases("fence_enabled"), pool.phrases("fence_disabled"))

    def test_multiple_phrases_do_not_repeat_consecutively(self):
        pool = DialoguePool({"event": ("a", "b", "c")}, chooser=lambda values: values[0])
        self.assertEqual(pool.get("event"), "a")
        self.assertEqual(pool.get("event"), "b")
        self.assertTrue(pool.last_avoided_repeat)

    def test_single_phrase_may_repeat(self):
        pool = DialoguePool({"event": ("only",)}, chooser=lambda values: values[0])
        self.assertEqual(pool.get("event"), "only")
        self.assertEqual(pool.get("event"), "only")


class FenceControllerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_external_drag_snaps_back_and_disable_restores_range(self):
        controller = PetController(object(), _Memory(), logger=Mock())
        controller._tick_timer.stop()
        controller.set_screen_bounds(0, 0, 1000, 800)
        controller.sync_geometry(400, 300, 100, 100)
        positions, complaints = [], []
        controller.position_requested.connect(lambda x, y: positions.append((x, y)))
        controller.local_message_requested.connect(complaints.append)
        controller.enable_fence()
        self.assertIn(complaints[-1], controller.fence.dialogues.phrases("fence_enabled"))
        complaints.clear()
        positions.clear()

        controller.on_pet_drag_started()
        controller.on_pet_drag_moved(0, 0, 100, 100)
        controller.on_pet_dragged(0, 0, 100, 100)

        self.assertTrue(controller.fence.contains_pet(
            controller.movement.position.x, controller.movement.position.y, 100, 100
        ))
        self.assertTrue(positions)
        self.assertEqual(len(complaints), 1)
        self.assertIn(complaints[0], controller.fence.dialogues.phrases("fence_snapback"))

        controller.disable_fence()
        self.assertIn(complaints[-1], controller.fence.dialogues.phrases("fence_disabled"))
        controller.on_pet_drag_started()
        controller.on_pet_drag_moved(0, 0, 100, 100)
        controller.on_pet_dragged(0, 0, 100, 100)
        self.assertEqual(controller.movement.position, Vec2(0, 0))
        controller.shutdown()
    def make_controller(self):
        controller = PetController(object(), _Memory(), logger=Mock())
        controller._tick_timer.stop()
        controller.set_screen_bounds(0, 0, 1000, 800)
        controller.sync_geometry(400, 300, 100, 100)
        controller.enable_fence()
        return controller

    def test_dragging_outside_pauses_tick_clamp_and_complaint(self):
        controller = self.make_controller()
        messages = []
        controller.local_message_requested.connect(messages.append)
        controller.on_pet_drag_started()
        controller.on_pet_drag_moved(0, 0, 100, 100)
        outside = Vec2(controller.movement.position.x, controller.movement.position.y)

        controller._tick()

        self.assertEqual(controller.movement.position, outside)
        self.assertFalse(controller.fence.contains_pet(outside.x, outside.y, 100, 100))
        self.assertEqual(messages, [])
        controller.on_pet_drag_cancelled()
        controller.shutdown()

    def test_release_inside_has_no_snapback_or_complaint(self):
        controller = self.make_controller()
        positions, messages = [], []
        controller.position_requested.connect(lambda x, y: positions.append((x, y)))
        controller.local_message_requested.connect(messages.append)
        x, y = controller.fence.clamp_point(420, 320, 100, 100)
        controller.on_pet_drag_started()
        controller.on_pet_drag_moved(x, y, 100, 100)

        controller.on_pet_dragged(x, y, 100, 100)

        self.assertEqual(positions, [])
        self.assertEqual(messages, [])
        controller.shutdown()

    def test_one_drag_release_snapbacks_and_complains_at_most_once(self):
        controller = self.make_controller()
        positions, messages = [], []
        controller.position_requested.connect(lambda x, y: positions.append((x, y)))
        controller.local_message_requested.connect(messages.append)
        controller.on_pet_drag_started()
        controller.on_pet_drag_moved(0, 0, 100, 100)

        controller.on_pet_dragged(0, 0, 100, 100)
        controller.on_pet_dragged(0, 0, 100, 100)

        self.assertEqual(len(positions), 1)
        self.assertEqual(len(messages), 1)
        self.assertLessEqual(controller.behavior._next_decision - monotonic(), 0.5)
        controller.shutdown()

    def test_snapback_complaint_still_obeys_cooldown(self):
        controller = self.make_controller()
        messages = []
        controller.local_message_requested.connect(messages.append)
        for _ in range(2):
            controller.on_pet_drag_started()
            controller.on_pet_drag_moved(0, 0, 100, 100)
            controller.on_pet_dragged(0, 0, 100, 100)
        self.assertEqual(len(messages), 1)
        controller.shutdown()

    def test_user_edited_rect_is_clamped_and_keeps_pet_inside(self):
        controller = self.make_controller()
        final_rect = controller.update_fence_rect((-200, -100, 120, 140))
        self.assertEqual(final_rect.left, 0)
        self.assertEqual(final_rect.top, 0)
        self.assertTrue(controller.fence.contains_pet(
            controller.movement.position.x, controller.movement.position.y, 100, 100
        ))
        controller.shutdown()


class FenceOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.overlay = FenceOverlayWindow()

    def tearDown(self):
        self.overlay.close()

    def test_rect_and_updates_match_fence_bounds(self):
        self.overlay.update_rect(Bounds(100, 120, 460, 380))
        self.assertEqual(self.overlay.geometry().getRect(), (100, 120, 360, 260))
        self.overlay.update_rect(Bounds(20, 30, 220, 180))
        self.assertEqual(self.overlay.geometry().getRect(), (20, 30, 200, 150))

    def test_overlay_is_non_focusing_and_click_through(self):
        flags = self.overlay.windowFlags()
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(flags & Qt.WindowType.Tool)
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(flags & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertTrue(self.overlay.testAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating
        ))

    def test_drag_geometry_moves_and_resizes(self):
        start = QRect(100, 120, 360, 260)
        self.assertEqual(
            self.overlay._geometry_for_drag(start, QPoint(30, -20), "move"),
            QRect(130, 100, 360, 260),
        )
        self.assertEqual(
            self.overlay._geometry_for_drag(start, QPoint(40, 25), "bottom_right"),
            QRect(100, 120, 400, 285),
        )

    def test_top_center_is_move_handle_and_edges_are_resize_handles(self):
        self.overlay.resize(360, 260)
        self.assertEqual(self.overlay._interaction_at(QPoint(180, 2)), "move")
        self.assertEqual(self.overlay._interaction_at(QPoint(2, 2)), "top_left")
        self.assertEqual(self.overlay._interaction_at(QPoint(2, 130)), "left")

    def test_pet_window_shows_and_hides_overlay_with_fence(self):
        controller = PetController(object(), _Memory(), logger=Mock())
        controller._tick_timer.stop()
        window = PetWindow(
            controller, Path(__file__).resolve().parents[1] / "assets",
            options={"width": 100, "height": 120},
            fence_options={"show_overlay": True},
        )
        controller.enable_fence()
        QApplication.processEvents()
        self.assertTrue(window.fence_overlay.isVisible())
        rect = controller.fence.rect
        self.assertIsNotNone(rect)
        self.assertEqual(
            window.fence_overlay.geometry().getRect(),
            (round(rect.left), round(rect.top), round(rect.right - rect.left),
             round(rect.bottom - rect.top)),
        )
        controller.disable_fence()
        QApplication.processEvents()
        self.assertFalse(window.fence_overlay.isVisible())
        window.close()


if __name__ == "__main__":
    unittest.main()
