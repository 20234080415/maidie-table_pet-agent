from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.settings import ConfigStore


class ConfigStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "config.json"
        self.path.write_text(json.dumps({
            "ai": {"provider": "deepseek", "api_key": "secret-value", "base_url": "https://old", "model": "old-chat"},
            "codex": {"model": "old-tech"},
            "personality": {"preset": "gentle_tsundere", "custom_prompt": ""},
            "window": {"width": 160},
        }), encoding="utf-8")
        self.store = ConfigStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_public_view_never_exposes_key(self):
        public = self.store.public_settings()
        self.assertTrue(public["has_api_key"])
        self.assertNotIn("api_key", public)
        self.assertNotIn("secret-value", repr(public))

    def test_update_preserves_key_when_input_is_blank(self):
        self.store.update_user_settings({
            "provider": "deepseek", "base_url": "https://api.deepseek.com",
            "chat_model": "new-chat", "technical_model": "new-tech",
            "api_key": "", "personality_preset": "healing", "custom_personality": "",
        })
        saved = self.store.load()
        self.assertEqual(saved["ai"]["api_key"], "secret-value")
        self.assertEqual(saved["ai"]["model"], "new-chat")
        self.assertIn("安静", self.store.personality_prompt(saved))
        self.assertEqual(saved["window"]["width"], 160)

    def test_missing_network_settings_use_safe_defaults(self):
        saved = self.store.load()
        self.assertFalse(saved["network"]["enabled"])
        self.assertEqual(saved["network"]["timeout"], 10)
        self.assertNotIn("network_search_api_key", self.store.public_settings())

    def test_proactive_behavior_is_disabled_by_default(self):
        saved = self.store.load()
        public = self.store.public_settings()
        self.assertFalse(saved["proactive"]["enabled"])
        self.assertFalse(public["proactive_enabled"])
        self.assertEqual(public["proactive_tick_seconds"], 45)
        self.assertFalse(public["screen_awareness_enabled"])

    def test_fence_overlay_is_enabled_by_default(self):
        self.assertTrue(self.store.load()["fence"]["show_overlay"])

    def test_vision_settings_save_without_exposing_key(self):
        self.store.update_user_settings({
            "vision_workspace_id": "ws-123",
            "vision_api_key": "vision-secret",
            "vision_model": "qwen3-vl-flash",
            "vision_region": "cn-beijing",
            "vision_max_width": 1024,
            "vision_jpeg_quality": 80,
            "vision_cache_ttl_seconds": 8,
        })
        saved = self.store.load()["vision"]
        public = self.store.public_settings()
        self.assertEqual(saved["workspace_id"], "ws-123")
        self.assertEqual(saved["api_key"], "vision-secret")
        self.assertEqual(public["vision_max_width"], 1024)
        self.assertTrue(public["has_vision_api_key"])
        self.assertNotIn("vision-secret", repr(public))


if __name__ == "__main__":
    unittest.main()
