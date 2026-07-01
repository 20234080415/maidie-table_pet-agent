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

    def test_missing_config_is_copied_from_default(self):
        target = Path(self.temp.name) / "new" / "config.json"
        default = Path(self.temp.name) / "default.json"
        default.write_text(json.dumps({"ai": {"api_key": ""}}), encoding="utf-8")
        loaded = ConfigStore(target, default).load()
        self.assertEqual(loaded, {"ai": {"api_key": ""}})
        self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
