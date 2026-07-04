from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from animation.model_manager import AnimationModelRegistry


class Live2DPetWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._setup_model_and_viewer()

    def tearDown(self):
        self.temp.cleanup()

    def _setup_model_and_viewer(self):
        model_path = self.root / "A" / "a.model3.json"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text("{}", encoding="utf-8")
        viewer = self.root / "viewer"
        viewer.mkdir()
        (viewer / "index.html").write_text("viewer", encoding="utf-8")
        self.model = AnimationModelRegistry().import_model3_json(model_path, root=self.root)
        self.viewer = viewer

    def test_live2d_pet_window_class_is_importable(self):
        from ui.live2d_pet_window import Live2DPetWindow, create_live2d_pet_window, pet_window_available
        self.assertTrue(callable(create_live2d_pet_window))
        self.assertIsInstance(pet_window_available(), bool)

    def test_missing_webengine_returns_structured_error_without_crash(self):
        with patch("ui.live2d_pet_window.WEBENGINE_AVAILABLE", False):
            from ui.live2d_pet_window import create_live2d_pet_window
            window, result = create_live2d_pet_window(self.model)
        self.assertIsNone(window)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "webengine_missing")

    def test_null_model_returns_error(self):
        from ui.live2d_pet_window import create_live2d_pet_window
        window, result = create_live2d_pet_window(None)
        self.assertIsNone(window)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "model_not_selected")

    def test_missing_model_file_returns_error(self):
        model = AnimationModelRegistry().import_model3_json(
            self.root / "A" / "a.model3.json", root=self.root
        )
        model_path = Path(model.model3_json)
        model_path.unlink()
        with patch("ui.live2d_pet_window.WEBENGINE_AVAILABLE", True):
            from ui.live2d_pet_window import create_live2d_pet_window
            window, result = create_live2d_pet_window(model)
        self.assertIsNone(window)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "model_missing")

    def test_missing_viewer_returns_error(self):
        with patch("ui.live2d_pet_window.WEBENGINE_AVAILABLE", True), \
                patch("ui.live2d_pet_window.viewer_root") as vroot:
            vroot.return_value = self.root / "nonexistent"
            from ui.live2d_pet_window import create_live2d_pet_window
            window, result = create_live2d_pet_window(self.model)
        self.assertIsNone(window)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "viewer_missing")

    def test_create_function_handles_generic_exception(self):
        with patch("ui.live2d_pet_window.WEBENGINE_AVAILABLE", True), \
                patch("ui.live2d_pet_window.viewer_root") as vroot, \
                patch("ui.live2d_pet_window.Live2DPetWindow", side_effect=RuntimeError("test boom")):
            vroot.return_value = self.viewer
            from ui.live2d_pet_window import create_live2d_pet_window
            window, result = create_live2d_pet_window(self.model)
        self.assertIsNone(window)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "pet_window_creation_failed")
        self.assertIn("test boom", result["error"])

    def test_backend_with_sink_calls_apply_state_for_speaking_confused_success_error(self):
        from animation.live2d_backend import Live2DBackend
        from animation.live2d_preview_server import Live2DPreviewServer

        server = Live2DPreviewServer(self.model, viewer=self.viewer, lifetime_seconds=60)
        try:
            server.start()
            captured = []
            backend = Live2DBackend(
                command_sink=lambda cmd: (captured.append(cmd), server.enqueue_command(server.session_id, cmd))[1]
            )
            for state in ("speaking", "confused", "success", "error"):
                result = backend.apply_state(state)
                self.assertTrue(result["ok"], f"apply_state({state}) failed")
                self.assertTrue(result["delivered"], f"apply_state({state}) not delivered")
                self.assertEqual(result["command"], "applySemanticState")
            self.assertEqual(len(captured), 4)
            commands = server.drain_commands(server.session_id)
            self.assertEqual(len(commands), 4)
        finally:
            server.stop()

    def test_backend_shuts_down_and_rejects_after_shutdown(self):
        from animation.live2d_backend import Live2DBackend
        from animation.live2d_preview_server import Live2DPreviewServer

        server = Live2DPreviewServer(self.model, viewer=self.viewer, lifetime_seconds=60)
        try:
            server.start()
            backend = Live2DBackend(
                command_sink=lambda cmd: server.enqueue_command(server.session_id, cmd)
            )
            backend.apply_state("idle")
            shutdown = backend.shutdown()
            self.assertEqual(shutdown["command"], "shutdown")
            rejected = backend.apply_state("confused")
            self.assertFalse(rejected["ok"])
            self.assertFalse(rejected["queued"])
            self.assertIn("shut down", rejected["error"])
        finally:
            server.stop()

    def test_pet_window_creation_success(self):
        with patch("ui.live2d_pet_window.WEBENGINE_AVAILABLE", True), \
                patch("ui.live2d_pet_window.viewer_root") as vroot:
            vroot.return_value = self.viewer
            mock_window = MagicMock()
            with patch("ui.live2d_pet_window.Live2DPetWindow", return_value=mock_window):
                from ui.live2d_pet_window import create_live2d_pet_window
                window, result = create_live2d_pet_window(self.model)
            self.assertIs(window, mock_window)
            self.assertTrue(result["ok"])
            self.assertEqual(result["code"], "pet_window_opened")

    def test_default_backend_remains_sprite(self):
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
            self.assertEqual(store.public_settings()["animation_backend"], "sprite")
        finally:
            temp.cleanup()

    def test_pet_window_does_not_replace_sprite_main_pet(self):
        from animation.live2d_web import resolve_animation_backend
        backend, status = resolve_animation_backend({"backend": "sprite"})
        self.assertEqual(backend, "sprite")
        backend2, status2 = resolve_animation_backend(None)
        self.assertEqual(backend2, "sprite")

    def test_main_module_has_webengine_prepare_function(self):
        import main
        self.assertTrue(callable(main._prepare_webengine))
        self.assertTrue(callable(main.webengine_ready))

    def test_webengine_prepare_sets_share_opengl_attribute(self):
        import main
        from PyQt6.QtCore import QCoreApplication, Qt
        saved = main._webengine_ready
        try:
            main._prepare_webengine()
        finally:
            main._webengine_ready = saved

    def test_sprite_still_starts_when_webengine_missing(self):
        import main
        from PyQt6.QtCore import QCoreApplication, Qt
        saved = main._webengine_ready
        try:
            main._webengine_ready = False
            self.assertFalse(main.webengine_ready())
        finally:
            main._webengine_ready = saved

    def test_live2d_preview_process_imports_webengine_before_qapp(self):
        source = (Path(__file__).parents[1] / "ui" / "live2d_preview_process.py").read_text(
            encoding="utf-8"
        )
        webengine_line = -1
        qapp_line = -1
        for i, line in enumerate(source.splitlines()):
            if "QtWebEngineWidgets" in line and ("import" in line or "from" in line):
                webengine_line = i
            if "QApplication(" in line and webengine_line >= 0:
                qapp_line = i
                break
        self.assertGreater(webengine_line, 0, "No QtWebEngineWidgets import found")
        self.assertGreater(qapp_line, 0, "No QApplication(...) creation found")
        self.assertLess(webengine_line, qapp_line,
                        "QtWebEngineWidgets must be imported before QApplication()")


class SettingsLive2DLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def _dialog(self):
        from PyQt6.QtWidgets import QDialog
        from ui.dialogs import SettingsDialog
        dialog = SettingsDialog.__new__(SettingsDialog)
        QDialog.__init__(dialog)
        dialog._live2d_scan_thread = None
        dialog._install_thread = None
        dialog._live2d_pet_window = None
        dialog._live2d_appearance_window = None
        dialog._live2d_preview_windows = []
        dialog._live2d_preview_servers = []
        return dialog

    def _attach_live2d_resources(self, dialog):
        resources = [MagicMock(), MagicMock(), MagicMock()]
        server = MagicMock()
        dialog._live2d_pet_window = resources[0]
        dialog._live2d_appearance_window = resources[1]
        dialog._live2d_preview_windows = [resources[2]]
        dialog._live2d_preview_servers = [server]
        return resources, server

    def _assert_cleaned(self, dialog, resources, server):
        for resource in resources:
            resource.close.assert_called_once()
        server.stop.assert_called_once()
        self.assertIsNone(dialog._live2d_pet_window)
        self.assertIsNone(dialog._live2d_appearance_window)
        self.assertEqual(dialog._live2d_preview_windows, [])
        self.assertEqual(dialog._live2d_preview_servers, [])

    def test_accept_cleans_live2d_resources(self):
        dialog = self._dialog()
        resources, server = self._attach_live2d_resources(dialog)
        dialog.accept()
        self._assert_cleaned(dialog, resources, server)

    def test_reject_cleans_live2d_resources(self):
        dialog = self._dialog()
        resources, server = self._attach_live2d_resources(dialog)
        dialog.reject()
        self._assert_cleaned(dialog, resources, server)

    def test_close_event_cleans_live2d_resources_idempotently(self):
        from PyQt6.QtGui import QCloseEvent
        dialog = self._dialog()
        resources, server = self._attach_live2d_resources(dialog)
        dialog.closeEvent(QCloseEvent())
        dialog._cleanup_live2d_windows()
        self._assert_cleaned(dialog, resources, server)

    def test_reopening_appearance_closes_old_window_without_touching_debug(self):
        dialog = self._dialog()
        old_appearance = MagicMock()
        debug_window = MagicMock()
        new_appearance = MagicMock()
        model = MagicMock(id="model-id")
        dialog._live2d_appearance_window = old_appearance
        dialog._live2d_pet_window = debug_window
        dialog.live2d_model = MagicMock()
        dialog.live2d_model.currentData.return_value = "model-id"
        dialog.live2d_registry = MagicMock()
        dialog.live2d_registry.list_models.return_value = [model]
        dialog.live2d_preview_label = MagicMock()
        with patch("ui.dialogs.create_live2d_pet_window",
                   return_value=(new_appearance, {"ok": True, "message": "opened"})):
            dialog._open_live2d_appearance_window()
        old_appearance.close.assert_called_once()
        self.assertIs(dialog._live2d_appearance_window, new_appearance)
        self.assertIs(dialog._live2d_pet_window, debug_window)

    def test_reopening_debug_closes_old_window_without_touching_appearance(self):
        dialog = self._dialog()
        old_debug = MagicMock()
        appearance_window = MagicMock()
        new_debug = MagicMock()
        model = MagicMock(id="model-id")
        dialog._live2d_pet_window = old_debug
        dialog._live2d_appearance_window = appearance_window
        dialog.live2d_model = MagicMock()
        dialog.live2d_model.currentData.return_value = "model-id"
        dialog.live2d_registry = MagicMock()
        dialog.live2d_registry.list_models.return_value = [model]
        dialog.live2d_preview_label = MagicMock()
        with patch("ui.dialogs.create_live2d_pet_window",
                   return_value=(new_debug, {"ok": True, "message": "opened"})):
            dialog._open_live2d_pet_window()
        old_debug.close.assert_called_once()
        self.assertIs(dialog._live2d_pet_window, new_debug)
        self.assertIs(dialog._live2d_appearance_window, appearance_window)

    def test_close_button_closes_debug_and_appearance_independently(self):
        dialog = self._dialog()
        debug_window = MagicMock()
        appearance_window = MagicMock()
        dialog._live2d_pet_window = debug_window
        dialog._live2d_appearance_window = appearance_window
        dialog.live2d_preview_label = MagicMock()
        dialog._close_live2d_pet_window()
        debug_window.close.assert_called_once()
        appearance_window.close.assert_called_once()
        self.assertIsNone(dialog._live2d_pet_window)
        self.assertIsNone(dialog._live2d_appearance_window)


if __name__ == "__main__":
    unittest.main()
