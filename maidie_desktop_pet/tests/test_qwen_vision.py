from __future__ import annotations

import unittest
import os
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from PIL import Image

from core.brain.fast_route import fast_route
from core.vision import QwenVLClient, VisionContext, VisionService
from core.vision.image_preprocess import preprocess_for_vl, resize_image


class VisionContextTests(unittest.TestCase):
    def test_normal_and_missing_fields(self):
        context = VisionContext.from_dict({"screen_summary": "IDE", "confidence": 4})
        self.assertEqual(context.screen_summary, "IDE")
        self.assertEqual(context.task_type, "unknown")
        self.assertEqual(context.confidence, 1.0)

    def test_fallback(self):
        context = VisionContext.fallback("not json", (10, 20))
        self.assertEqual(context.raw_response, "not json")
        self.assertEqual(context.image_size, (10, 20))
        self.assertEqual(context.confidence, 0.0)


class ImagePreprocessTests(unittest.TestCase):
    def test_jpeg_data_url_and_resize(self):
        image = Image.new("RGBA", (2000, 1000), (1, 2, 3, 100))
        data_url, size, byte_size = preprocess_for_vl(image, 1280, 85)
        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        self.assertEqual(size, (1280, 640))
        self.assertGreater(byte_size, 0)

    def test_small_image_is_not_enlarged(self):
        image = Image.new("RGB", (200, 100))
        self.assertEqual(resize_image(image, 1280).size, (200, 100))


class QwenClientTests(unittest.TestCase):
    @staticmethod
    def _factory(content):
        response = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=content)
        )])
        client = Mock()
        client.chat.completions.create.return_value = response
        return Mock(return_value=client)

    def test_valid_json_is_parsed(self):
        raw = ('{"screen_summary":"traceback","visible_text":"ValueError",'
               '"task_type":"code_error","important_regions":["terminal"],'
               '"user_intent_guess":"debug","confidence":0.9}')
        client = QwenVLClient("key", "workspace", client_factory=self._factory(raw))
        result = client.analyze_image("data:image/jpeg;base64,AA==", "看看报错")
        self.assertEqual(result.task_type, "code_error")

    def test_invalid_json_falls_back(self):
        client = QwenVLClient("key", "workspace", client_factory=self._factory("oops"))
        result = client.analyze_image("data:image/jpeg;base64,AA==", "看看")
        self.assertEqual(result.task_type, "unknown")
        self.assertEqual(result.raw_response, "oops")


class VisionServiceTests(unittest.TestCase):
    def test_short_repeat_hits_cache(self):
        capture = Mock()
        capture.capture_active_window.return_value = Image.new("RGB", (20, 10))
        client = Mock()
        client.analyze_image.return_value = VisionContext(screen_summary="screen")
        service = VisionService(capture, client, cache_ttl_seconds=5, clock=lambda: 10)
        first = service.capture_and_analyze("first")
        second = service.capture_and_analyze("followup")
        self.assertIs(first, second)
        capture.capture_active_window.assert_called_once_with()
        client.analyze_image.assert_called_once()

    def test_saved_settings_reconfigure_client(self):
        client = QwenVLClient("old", "old-workspace")
        service = VisionService(client=client)
        with patch.dict(os.environ, {}, clear=True):
            service.reconfigure({
                "api_key": "new-key", "workspace_id": "new-workspace",
                "model": "qwen3-vl-flash", "region": "cn-beijing",
                "max_width": 900, "jpeg_quality": 77, "cache_ttl_seconds": 9,
            })
        self.assertEqual(client.api_key, "new-key")
        self.assertEqual(client.workspace_id, "new-workspace")
        self.assertEqual(service.max_width, 900)
        self.assertEqual(service.cache_ttl_seconds, 9)


class VisionRouteTests(unittest.TestCase):
    def test_explicit_screen_question_is_vision(self):
        route = fast_route("你看看我现在屏幕这个题怎么写")
        self.assertEqual(route["intent"], "vision")
        self.assertTrue(route["need_screen"])

    def test_chat_is_not_vision(self):
        route = fast_route("我今天有点累")
        self.assertTrue(route is None or route["intent"] != "vision")

    def test_ambiguous_request_does_not_capture(self):
        route = fast_route("这个怎么弄")
        self.assertEqual(route["intent"], "clarification")
        self.assertFalse(route["need_screen"])


if __name__ == "__main__":
    unittest.main()
