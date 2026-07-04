from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from animation.live2d_web import (Live2DWebPreview, resolve_animation_backend,
                                  runtime_status, viewer_root)
from animation.model_manager import AnimationModelRegistry
from core.settings import ConfigStore


class AnimationModelRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _model_file(self, relative: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return path

    def test_scan_model_root_finds_nested_models(self):
        self._model_file("Hibiki/runtime/hibiki.model3.json")
        self._model_file("Hiyori/free/runtime/hiyori_free.model3.json")
        registry = AnimationModelRegistry()
        models = registry.scan_model_root(self.root)
        self.assertEqual(len(models), 2)
        self.assertEqual(len(registry.list_models()), 2)
        self.assertTrue(all(model.backend == "live2d_web" for model in models))

    def test_missing_model_returns_error_without_corrupting_registry(self):
        registry = AnimationModelRegistry()
        with self.assertRaises(FileNotFoundError):
            registry.import_model3_json(self.root / "missing.model3.json")
        self.assertEqual(registry.list_models(), [])
        self.assertIsNone(registry.resolve_current_model())

    def test_current_model_can_be_switched(self):
        first = self._model_file("A/a.model3.json")
        second = self._model_file("B/b.model3.json")
        registry = AnimationModelRegistry()
        first_model = registry.import_model3_json(first, root=self.root)
        second_model = registry.import_model3_json(second, root=self.root)
        registry.set_current_model(first_model.id)
        self.assertEqual(registry.resolve_current_model(), first_model)
        registry.set_current_model(second_model.id)
        self.assertEqual(registry.resolve_current_model(), second_model)

    def test_missing_webengine_falls_back_without_import_failure(self):
        model = AnimationModelRegistry().import_model3_json(
            self._model_file("A/a.model3.json"), root=self.root
        )
        with patch("animation.live2d_web.find_spec", return_value=None):
            status = Live2DWebPreview().inspect(model)
            backend, runtime_status = resolve_animation_backend({
                "backend": "live2d_web",
                "current_model_id": model.id,
                "live2d_models": [model.to_dict()],
            })
        self.assertFalse(status.available)
        self.assertEqual(backend, "sprite")
        self.assertIn("WebEngine", runtime_status.message)

    def test_missing_runtime_is_reported_instead_of_fake_success(self):
        model = AnimationModelRegistry().import_model3_json(
            self._model_file("A/a.model3.json"), root=self.root
        )
        empty_viewer = self.root / "viewer"
        empty_viewer.mkdir()
        (empty_viewer / "index.html").write_text("<html></html>", encoding="utf-8")
        with patch("animation.live2d_web.find_spec", return_value=object()):
            status = Live2DWebPreview().inspect(
                model, require_runtime=True, root=empty_viewer
            )
        self.assertFalse(status.available)
        self.assertEqual(status.code, "runtime_missing")
        self.assertIn("Live2D Web Runtime is not installed", status.message)
        self.assertEqual(len(status.details["missing_files"]), 3)

    def test_viewer_exposes_required_javascript_api(self):
        html = (viewer_root() / "index.html").read_text(encoding="utf-8")
        self.assertIn("window.loadModel", html)
        self.assertIn("window.setExpression", html)
        self.assertIn("window.setParameter", html)
        empty_runtime = self.root / "empty-viewer"
        empty_runtime.mkdir()
        installed, missing = runtime_status(empty_runtime)
        self.assertFalse(installed)
        self.assertTrue(missing)

    def test_preview_dialog_module_imports_without_webengine(self):
        with patch("animation.live2d_web.find_spec", return_value=None):
            import ui.live2d_preview_dialog as preview_dialog
            self.assertTrue(callable(preview_dialog.create_live2d_preview_dialog))

    def test_preview_creation_failure_is_structured(self):
        model = AnimationModelRegistry().import_model3_json(
            self._model_file("A/a.model3.json"), root=self.root
        )
        from ui import live2d_preview_dialog as preview_dialog
        with patch.object(preview_dialog, "Live2DPreviewDialog",
                          side_effect=RuntimeError("preview boom")):
            dialog, result = preview_dialog.create_live2d_preview_dialog(model)
        self.assertIsNone(dialog)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "preview_creation_failed")
        self.assertIn("preview boom", result["details"]["error"])

    def test_missing_model_preview_is_structured(self):
        from ui.live2d_preview_dialog import create_live2d_preview_dialog
        dialog, result = create_live2d_preview_dialog(None)
        self.assertIsNone(dialog)
        self.assertEqual(result["code"], "model_not_selected")


class AnimationConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "config.json"
        self.base = {
            "ai": {"api_key": "", "base_url": "https://example", "model": "chat"},
            "codex": {"model": "tech"},
            "personality": {"preset": "gentle_tsundere", "custom_prompt": ""},
            "workspace": {"root": "D:/workspace"},
            "coding_agent": {"enabled": True, "provider": "codex", "command": "codex",
                             "timeout_seconds": 90, "idle_timeout_seconds": 30,
                             "dry_run": True},
            "custom_memory_setting": {"keep": True},
        }
        self.path.write_text(json.dumps(self.base), encoding="utf-8")
        self.store = ConfigStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_backend_is_sprite_and_missing_config_is_completed(self):
        animation = self.store.load()["animation"]
        self.assertEqual(animation, {
            "backend": "sprite", "current_model_id": "",
            "live2d_model_root": "", "live2d_models": [],
        })
        self.assertEqual(self.store.public_settings()["animation_backend"], "sprite")

    def test_animation_update_preserves_agent_tool_memory_and_coding_settings(self):
        before = self.store.load()
        self.store.update_user_settings({
            "animation_backend": "live2d_web",
            "animation_current_model_id": "model-a",
            "animation_live2d_model_root": "D:/external/live2d",
            "animation_live2d_models": [{"id": "model-a"}],
        })
        after = self.store.load()
        self.assertEqual(after["workspace"], before["workspace"])
        self.assertEqual(after["coding_agent"], before["coding_agent"])
        self.assertEqual(after["custom_memory_setting"], before["custom_memory_setting"])
        self.assertNotIn("tools", after["animation"])

    def test_packaging_config_contains_no_local_model_path(self):
        config = json.loads((Path(__file__).parents[1] / "packaging" / "config.json")
                            .read_text(encoding="utf-8"))
        animation = config["animation"]
        self.assertEqual(animation["backend"], "sprite")
        self.assertEqual(animation["live2d_model_root"], "")
        self.assertEqual(animation["live2d_models"], [])
        self.assertNotIn("桌宠", json.dumps(animation, ensure_ascii=False))

    def test_preview_does_not_change_default_backend_or_other_config(self):
        before = self.store.load()
        from ui.live2d_preview_dialog import create_live2d_preview_dialog
        dialog, result = create_live2d_preview_dialog(None)
        after = self.store.load()
        self.assertIsNone(dialog)
        self.assertFalse(result["ok"])
        self.assertEqual(after["animation"]["backend"], "sprite")
        self.assertEqual(after["workspace"], before["workspace"])
        self.assertEqual(after["coding_agent"], before["coding_agent"])
        self.assertEqual(after["custom_memory_setting"], before["custom_memory_setting"])


if __name__ == "__main__":
    unittest.main()
