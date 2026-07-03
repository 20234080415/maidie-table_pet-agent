from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.prompts.personality import PERSONALITY_PRESETS, build_personality_prompt
from core.settings import ConfigStore


class PersonalityPromptTests(unittest.TestCase):
    def test_every_preset_builds_a_non_empty_prompt(self):
        for preset_id in PERSONALITY_PRESETS:
            with self.subTest(preset_id=preset_id):
                self.assertTrue(build_personality_prompt(preset_id).strip())

    def test_custom_prompt_takes_priority(self):
        custom = "你是一位说话简洁、喜欢用比喻的桌面伙伴。"
        self.assertEqual(build_personality_prompt("custom", custom), custom)

    def test_unknown_preset_falls_back_to_gentle_tsundere(self):
        self.assertEqual(
            build_personality_prompt("missing-preset"),
            build_personality_prompt("gentle_tsundere"),
        )


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

    def test_personality_prompt_supports_legacy_config_fields(self):
        legacy = {"personality": {"preset": "custom", "custom_prompt": "保持冷静简洁。"}}
        self.assertEqual(self.store.personality_prompt(legacy), "保持冷静简洁。")

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
            "vision_default_scope": "cursor_region",
            "vision_cursor_region_width": 900,
            "vision_cursor_region_height": 700,
        })
        saved = self.store.load()["vision"]
        public = self.store.public_settings()
        self.assertEqual(saved["workspace_id"], "ws-123")
        self.assertEqual(saved["api_key"], "vision-secret")
        self.assertEqual(public["vision_max_width"], 1024)
        self.assertEqual(public["vision_default_scope"], "cursor_region")
        self.assertEqual(public["vision_cursor_region_width"], 900)
        self.assertTrue(public["has_vision_api_key"])
        self.assertNotIn("vision-secret", repr(public))


if __name__ == "__main__":
    unittest.main()
