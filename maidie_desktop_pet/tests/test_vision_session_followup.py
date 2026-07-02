from __future__ import annotations

import unittest
from unittest.mock import Mock

from PIL import Image

from core.brain import BrainRouter
from core.session.thinking_feedback import ThinkingFeedbackPool
from core.tools import ScreenTool, ToolRegistry
from core.vision import ScreenCapture, VisionContext, VisionService, VisionSession


class _Memory:
    def prompt_context(self): return ""


class _Client:
    api_key = "configured"

    def route_intent(self, _prompt, _context):
        return {"intent": "chat", "confidence": 1, "reason": "default chat"}

    def ask(self, _prompt, _context):
        return {"text": "分析完成", "emotion": "thinking",
                "action": "talk", "state": "talking"}


class VisionSessionTests(unittest.TestCase):
    def test_save_and_read_context(self):
        session = VisionSession(clock=lambda: 10)
        context = VisionContext(screen_summary="terminal", task_type="code_error",
                                confidence=0.8)
        session.update(context, "看看报错", scope="active_window")
        self.assertIs(session.get_context(), context)
        self.assertTrue(session.has_active_session())
        self.assertEqual(session.task_type, "code_error")

    def test_session_expires_after_ttl(self):
        now = [10.0]
        session = VisionSession(clock=lambda: now[0])
        session.update(VisionContext(screen_summary="screen"), "看看")
        now[0] = 131.0
        self.assertFalse(session.has_active_session(120))


class VisionInteractionTests(unittest.TestCase):
    def setUp(self):
        self.capture = Mock()
        self.capture.capture_active_window.return_value = Image.new("RGB", (40, 20))
        self.capture.capture_cursor_region.return_value = Image.new("RGB", (30, 20))
        self.vl_client = Mock()
        self.vl_client.analyze_image.return_value = VisionContext(
            screen_summary="IDE traceback", visible_text="ValueError",
            task_type="code_error", confidence=0.9,
        )
        self.service = VisionService(
            self.capture, self.vl_client, clock=lambda: 10, cursor_delay_seconds=0
        )
        client = _Client()
        registry = ToolRegistry([ScreenTool(vision_service=self.service)])
        self.router = BrainRouter(client, client, registry, _Memory())

    def test_follow_up_reuses_session_without_capture(self):
        self.router.route("你看看我现在屏幕这个报错")
        self.router.route("那怎么办")
        self.capture.capture_active_window.assert_called_once_with()
        self.assertEqual(self.vl_client.analyze_image.call_count, 1)

    def test_ambiguous_request_is_clarification(self):
        result = self.router.route("这个怎么弄")
        self.assertIn("当前屏幕", result["text"])
        self.capture.capture_active_window.assert_not_called()

    def test_confirmation_after_clarification_enters_vision(self):
        self.router.route("帮我看看")
        self.router.route("对")
        self.capture.capture_active_window.assert_called_once_with()

    def test_cursor_phrase_selects_cursor_region(self):
        self.router.route("看鼠标这块")
        self.capture.capture_cursor_region.assert_called_once_with()
        self.capture.capture_active_window.assert_not_called()

    def test_refresh_forces_new_capture(self):
        self.router.route("你看看我现在屏幕")
        self.router.route("重新看一下屏幕")
        self.assertEqual(self.capture.capture_active_window.call_count, 2)
        self.assertEqual(self.vl_client.analyze_image.call_count, 2)

    def test_clear_phrase_clears_session(self):
        self.router.route("你看看我现在屏幕")
        self.assertTrue(self.service.session.has_active_session())
        self.router.route("不用看了")
        self.assertFalse(self.service.session.has_active_session())

    def test_normal_chat_does_not_use_session(self):
        self.router.route("你看看我现在屏幕")
        self.router.route("我今天有点累")
        self.capture.capture_active_window.assert_called_once_with()


class CursorRegionTests(unittest.TestCase):
    def test_region_is_clamped_to_screen(self):
        calls = []

        def grabber(**kwargs):
            calls.append(kwargs)
            bbox = kwargs["bbox"]
            return Image.new("RGB", (bbox[2] - bbox[0], bbox[3] - bbox[1]))

        capture = ScreenCapture(
            grabber=grabber,
            cursor_provider=lambda: (5, 5),
            bounds_provider=lambda: (0, 0, 1920, 1080),
        )
        image = capture.capture_cursor_region(1000, 800)
        self.assertEqual(calls[0]["bbox"], (0, 0, 1000, 800))
        self.assertEqual(image.size, (1000, 800))

    def test_cursor_capture_waits_before_reading_pointer(self):
        capture = Mock()
        capture.capture_cursor_region.return_value = Image.new("RGB", (20, 20))
        client = Mock()
        client.analyze_image.return_value = VisionContext(screen_summary="button")
        sleeper = Mock()
        service = VisionService(
            capture, client, clock=lambda: 10, cursor_delay_seconds=3, sleeper=sleeper
        )
        service.capture_and_analyze("看鼠标这块", scope="cursor_region")
        sleeper.assert_called_once_with(3.0)
        capture.capture_cursor_region.assert_called_once_with()

    def test_cursor_request_explains_the_delay(self):
        pool = ThinkingFeedbackPool(chooser=lambda values: values[0])
        self.assertIn("三秒", pool.choose("看鼠标这块"))


if __name__ == "__main__":
    unittest.main()
