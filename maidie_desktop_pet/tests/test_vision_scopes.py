from __future__ import annotations

import unittest
from unittest.mock import Mock
from types import SimpleNamespace

from PIL import Image

from core.vision import ScreenCapture, VisionContext, VisionScope, VisionService
from core.vision.errors import VisionCaptureError
from core.vision.intent_rules import detect_vision_scope
from core.pet import PetController


class VisionScopeDetectionTests(unittest.TestCase):
    def test_scope_examples(self):
        cases = {
            "看一下全屏": VisionScope.FULLSCREEN,
            "看看整个屏幕": VisionScope.FULLSCREEN,
            "看鼠标这块": VisionScope.CURSOR_REGION,
            "这个按钮是什么意思": VisionScope.CURSOR_REGION,
            "我框选一下给你看": VisionScope.SELECTED_REGION,
            "选个区域": VisionScope.SELECTED_REGION,
            "你看看我现在屏幕这个报错什么意思": VisionScope.ACTIVE_WINDOW,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(detect_vision_scope(text), expected)

    def test_selected_region_has_highest_priority(self):
        self.assertEqual(
            detect_vision_scope("我从全屏里框选一个区域"), VisionScope.SELECTED_REGION
        )

    def test_controller_pauses_ai_until_region_is_selected(self):
        fake = SimpleNamespace(
            ai_session=SimpleNamespace(busy=False, submit=Mock()),
            local_message_requested=SimpleNamespace(emit=Mock()),
            region_selection_requested=SimpleNamespace(emit=Mock()),
        )
        PetController.submit_text(fake, "我框选一下给你看")
        fake.region_selection_requested.emit.assert_called_once_with("我框选一下给你看")
        fake.ai_session.submit.assert_not_called()

    def test_controller_cancel_does_not_submit_ai(self):
        fake = SimpleNamespace(
            _selected_region_rect=(1, 2, 30, 40),
            local_message_requested=SimpleNamespace(emit=Mock()),
        )
        PetController.cancel_region_selection(fake)
        self.assertIsNone(fake._selected_region_rect)
        fake.local_message_requested.emit.assert_called_once()


class RegionCaptureTests(unittest.TestCase):
    def test_capture_region_clamps_to_screen(self):
        calls = []

        def grabber(**kwargs):
            calls.append(kwargs["bbox"])
            return Image.new("RGB", (100, 100))

        capture = ScreenCapture(
            grabber=grabber, bounds_provider=lambda: (0, 0, 1920, 1080)
        )
        capture.capture_region(-50, -20, 150, 120)
        self.assertEqual(calls, [(0, 0, 100, 100)])

    def test_tiny_region_is_rejected(self):
        capture = ScreenCapture(bounds_provider=lambda: (0, 0, 100, 100))
        with self.assertRaises(VisionCaptureError):
            capture.capture_region(0, 0, 10, 10)

    def test_selected_region_does_not_use_cache(self):
        capture = Mock()
        capture.capture_region.return_value = Image.new("RGB", (100, 100))
        client = Mock()
        client.analyze_image.return_value = VisionContext(screen_summary="selection")
        service = VisionService(capture, client, clock=lambda: 10)
        rect = (10, 20, 100, 100)
        service.capture_and_analyze("first", "selected_region", selected_rect=rect)
        service.capture_and_analyze("second", "selected_region", selected_rect=rect)
        self.assertEqual(capture.capture_region.call_count, 2)
        self.assertEqual(client.analyze_image.call_count, 2)

    def test_selected_region_without_rect_never_calls_qwen(self):
        capture = Mock()
        client = Mock()
        service = VisionService(capture, client)
        with self.assertRaises(VisionCaptureError):
            service.capture_and_analyze("selection", "selected_region")
        client.analyze_image.assert_not_called()

    def test_different_scopes_do_not_share_cache(self):
        capture = Mock()
        capture.capture_active_window.return_value = Image.new("RGB", (100, 100))
        capture.capture_fullscreen.return_value = Image.new("RGB", (200, 100))
        client = Mock()
        client.analyze_image.return_value = VisionContext(screen_summary="screen")
        service = VisionService(capture, client, clock=lambda: 10)
        service.capture_and_analyze("window", "active_window")
        service.capture_and_analyze("full", "fullscreen")
        self.assertEqual(client.analyze_image.call_count, 2)


if __name__ == "__main__":
    unittest.main()
