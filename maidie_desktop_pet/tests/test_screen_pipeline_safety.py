from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from core.awareness import WindowTracker
from core.brain import BrainRouter, Synthesizer
from core.tools import ScreenTool, ToolRegistry
from core.vision import ScreenReader


class _Memory:
    def prompt_context(self): return ""


class _ChatClient:
    def route_intent(self, _prompt, _context):
        return {"intent": "chat", "confidence": 1, "reason": "wrong model route"}

    def ask(self, _prompt, _context):
        return {"text": "chat", "emotion": "idle", "action": "talk", "state": "talking"}


class ScreenPipelineSafetyTests(unittest.TestCase):
    def test_window_tracker_filters_self_and_keeps_external_window(self):
        windows = iter([
            {"title": "problem.py - Visual Studio Code", "pid": 900, "process_name": "Code"},
            {"title": "Maidie Desktop Pet", "pid": 100, "process_name": "python"},
        ])
        tracker = WindowTracker(info_provider=lambda: next(windows), self_pid=100)

        external = tracker.snapshot()
        filtered = tracker.snapshot()

        self.assertFalse(external["ignored_self_window"])
        self.assertTrue(filtered["ignored_self_window"])
        self.assertEqual(filtered["window_title"], "problem.py - Visual Studio Code")
        self.assertNotIn("Maidie", filtered["window_title"])

    def test_self_window_without_external_context_is_explicit(self):
        tracker = WindowTracker(info_provider=lambda: {
            "title": "Maidie", "pid": 100, "process_name": "python",
        }, self_pid=100)

        result = tracker.snapshot()

        self.assertTrue(result["ignored_self_window"])
        self.assertEqual(result["window_state"], "no_external_window")
        self.assertEqual(result["error"], "no_external_window")

    def test_explicit_screen_query_cannot_fall_back_to_chat(self):
        awareness = Mock()
        awareness.screen_awareness_snapshot.return_value = {
            "screen_text": "ValueError", "app": "Code", "window": "problem.py",
            "context": "coding",
        }
        client = _ChatClient()
        router = BrainRouter(client, client, ToolRegistry([ScreenTool(awareness)]), _Memory())

        result = router.route("这个报错怎么解决", [])

        awareness.screen_awareness_snapshot.assert_called_once_with()
        self.assertEqual(result["source"], "screen")

    def test_full_screen_capture_never_calls_pet_widget_grab(self):
        pet_window = Mock()
        image = object()
        with patch("PIL.ImageGrab.grab", return_value=image) as grab:
            result = ScreenReader._grab_screen()

        self.assertIs(result, image)
        grab.assert_called_once_with(all_screens=True)
        pet_window.grab.assert_not_called()

    def test_screen_tool_failure_is_structured(self):
        awareness = Mock()
        awareness.screen_awareness_snapshot.side_effect = PermissionError("capture denied")

        result = ScreenTool(awareness).run("screen")

        self.assertEqual(result["type"], "screen")
        self.assertEqual(result["raw"]["error_code"], "screen_tool_failed")
        self.assertEqual(result["raw"]["screen_debug"]["screenshot_source"], "failed")

    def test_synthesizer_reports_real_screen_failure(self):
        tool_data = [{
            "tool": "screen", "ok": False,
            "data": {"type": "screen", "source": "local", "raw": {
                "error": "OCR is disabled", "error_code": "ocr_disabled",
            }},
        }]
        synthesizer = Synthesizer(_ChatClient())

        result = synthesizer.synthesize("看看我的屏幕", "screen", {}, tool_data, "", [])

        self.assertIn("OCR", result["text"])
        self.assertIn("未启用", result["text"])
        self.assertNotIn("只能看到自己这个小窗口", result["text"])


if __name__ == "__main__":
    unittest.main()
