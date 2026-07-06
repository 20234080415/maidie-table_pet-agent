from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from animation.model_manager import AnimationModelRegistry


class BackendSwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        model_path = self.root / "A" / "a.model3.json"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text("{}", encoding="utf-8")
        viewer = self.root / "viewer"
        viewer.mkdir()
        (viewer / "index.html").write_text("viewer", encoding="utf-8")
        self.model = AnimationModelRegistry().import_model3_json(model_path, root=self.root)
        self.viewer = viewer

    def tearDown(self):
        self.temp.cleanup()

    def test_default_config_resolves_to_sprite(self):
        from animation.backend_selector import try_create_live2d_window
        window, result = try_create_live2d_window({})
        self.assertIsNone(window)
        self.assertEqual(result["code"], "backend_not_live2d")

    def test_sprite_backend_returns_none(self):
        from animation.backend_selector import try_create_live2d_window
        window, result = try_create_live2d_window({"backend": "sprite"})
        self.assertIsNone(window)
        self.assertEqual(result["code"], "backend_not_live2d")

    def test_live2d_backend_without_model_returns_error(self):
        from animation.backend_selector import try_create_live2d_window
        window, result = try_create_live2d_window({
            "backend": "live2d_web",
            "current_model_id": "nonexistent",
            "live2d_models": [],
        })
        self.assertIsNone(window)
        self.assertFalse(result["ok"])

    def test_live2d_backend_with_valid_model_attempts_window(self):
        mock_window = MagicMock()
        available_status = MagicMock(available=True)
        with patch("animation.backend_selector.resolve_animation_backend",
                   return_value=("live2d_web", available_status)), \
                patch("ui.live2d_pet_window.create_live2d_pet_window",
                      return_value=(mock_window, {"ok": True, "code": "pet_window_opened"})) as create:
            from animation.backend_selector import try_create_live2d_window
            window, result = try_create_live2d_window({
                "backend": "live2d_web",
                "current_model_id": self.model.id,
                "live2d_models": [self.model.to_dict()],
            })
            self.assertIs(window, mock_window)
            self.assertTrue(result["ok"])
            create.assert_called_once_with(self.model)

    def test_live2d_window_creation_failure_falls_back(self):
        available_status = MagicMock(available=True)
        with patch("animation.backend_selector.resolve_animation_backend",
                   return_value=("live2d_web", available_status)), \
                patch("ui.live2d_pet_window.create_live2d_pet_window",
                      return_value=(None, {"ok": False, "code": "webengine_missing", "message": "no webengine"})):
            from animation.backend_selector import try_create_live2d_window
            window, result = try_create_live2d_window({
                "backend": "live2d_web",
                "current_model_id": self.model.id,
                "live2d_models": [self.model.to_dict()],
            })
            self.assertIsNone(window)
            self.assertFalse(result["ok"])

    def test_resolve_backend_and_window_sprite(self):
        from animation.backend_selector import resolve_backend_and_window
        backend, status, window = resolve_backend_and_window({"backend": "sprite"})
        self.assertEqual(backend, "sprite")
        self.assertIsNone(window)

    def test_resolve_backend_and_window_live2d_returns_window(self):
        mock_window = MagicMock()
        available_status = MagicMock(available=True)
        with patch("animation.backend_selector.resolve_animation_backend",
                   return_value=("live2d_web", available_status)), \
                patch("ui.live2d_pet_window.create_live2d_pet_window",
                      return_value=(mock_window, {"ok": True, "code": "pet_window_opened"})):
            from animation.backend_selector import resolve_backend_and_window
            backend, status, window = resolve_backend_and_window({
                "backend": "live2d_web",
                "current_model_id": self.model.id,
                "live2d_models": [self.model.to_dict()],
            })
            self.assertEqual(backend, "live2d_web")
            self.assertIs(window, mock_window)

    def test_resolve_backend_falls_back_to_sprite_on_live2d_failure(self):
        available_status = MagicMock(available=True)
        with patch("animation.backend_selector.resolve_animation_backend",
                   return_value=("live2d_web", available_status)), \
                patch("ui.live2d_pet_window.create_live2d_pet_window",
                      return_value=(None, {"ok": False, "code": "webengine_missing", "message": "no webengine"})):
            from animation.backend_selector import resolve_backend_and_window
            backend, status, window = resolve_backend_and_window({
                "backend": "live2d_web",
                "current_model_id": self.model.id,
                "live2d_models": [self.model.to_dict()],
            })
            self.assertEqual(backend, "sprite")
            self.assertIsNone(window)

    def test_default_config_animation_backend_is_sprite(self):
        from core.settings import ConfigStore
        temp = tempfile.TemporaryDirectory()
        try:
            path = Path(temp.name) / "config.json"
            base = {
                "ai": {"api_key": "", "base_url": "https://example", "model": "chat"},
                "codex": {"model": "tech"},
                "personality": {"preset": "gentle_tsundere", "custom_prompt": ""},
                "workspace": {"root": "D:/workspace"},
                "coding_agent": {"enabled": True, "provider": "codex", "command": "codex",
                                "timeout_seconds": 90, "idle_timeout_seconds": 30,
                                "dry_run": True},
                "custom_memory_setting": {"keep": True},
            }
            path.write_text(json.dumps(base), encoding="utf-8")
            store = ConfigStore(path)
            animation = store.load()["animation"]
            self.assertEqual(animation["backend"], "sprite")
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
