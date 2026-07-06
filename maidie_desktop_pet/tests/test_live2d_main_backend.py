from __future__ import annotations

import unittest
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class MainBackendSelectionTests(unittest.TestCase):
    def setUp(self):
        self.controller = MagicMock()
        self.broker = MagicMock()
        self.logger = MagicMock()

    @staticmethod
    def status(code="ok", message="available"):
        return SimpleNamespace(code=code, message=message, available=code == "ok")

    @patch("main.PetWindow")
    @patch("main.resolve_animation_backend")
    def test_default_config_starts_sprite(self, resolve, sprite):
        import main
        resolve.return_value = ("sprite", self.status())
        sprite.return_value = MagicMock()
        window, backend, _status = main._create_main_window(
            {}, self.controller, self.broker, self.logger
        )
        self.assertIs(window, sprite.return_value)
        self.assertEqual(backend, "sprite")
        sprite.assert_called_once()

    @patch("ui.live2d_main_window.create_live2d_main_window")
    @patch("main.resolve_animation_backend")
    def test_valid_live2d_config_selects_live2d_main_window(self, resolve, create):
        import main
        resolve.return_value = ("live2d_web", self.status())
        live_window = MagicMock()
        create.return_value = (live_window, {"ok": True})
        config = {"animation": {
            "backend": "live2d_web", "current_model_id": "m",
            "live2d_models": [{"id": "m", "name": "M", "model3_json": "M.model3.json"}],
        }}
        with patch("main.AnimationModelRegistry") as registry:
            registry.return_value.resolve_current_model.return_value = MagicMock()
            window, backend, _status = main._create_main_window(
                config, self.controller, self.broker, self.logger
            )
        self.assertIs(window, live_window)
        self.assertEqual(backend, "live2d_web")

    @patch("main.PetWindow")
    @patch("main.resolve_animation_backend")
    def test_missing_webengine_falls_back_to_sprite(self, resolve, sprite):
        import main
        resolve.return_value = (
            "sprite", self.status("webengine_missing", "PyQt6-WebEngine missing")
        )
        window, backend, status = main._create_main_window(
            {"animation": {"backend": "live2d_web"}},
            self.controller, self.broker, self.logger,
        )
        self.assertEqual(backend, "sprite")
        self.assertEqual(status.code, "webengine_missing")
        self.logger.warning.assert_called_once()

    @patch("main.PetWindow")
    @patch("main.resolve_animation_backend")
    def test_missing_model_falls_back_to_sprite(self, resolve, sprite):
        import main
        resolve.return_value = (
            "sprite", self.status("model_not_selected", "model missing")
        )
        _window, backend, status = main._create_main_window(
            {"animation": {"backend": "live2d_web"}},
            self.controller, self.broker, self.logger,
        )
        self.assertEqual(backend, "sprite")
        self.assertEqual(status.code, "model_not_selected")

    def test_force_sprite_argument_overrides_live2d_without_mutating_config(self):
        import main
        config = {"animation": {"backend": "live2d_web", "current_model_id": "m"}}
        overridden = main.apply_safe_backend_override(config, True)
        self.assertEqual(overridden["animation"]["backend"], "sprite")
        self.assertEqual(config["animation"]["backend"], "live2d_web")
        self.assertTrue(main.force_sprite_requested(["--force-sprite"]))


class MainWindowMenuTests(unittest.TestCase):
    def window(self):
        controller = MagicMock()
        controller.logger = MagicMock()
        return SimpleNamespace(controller=controller, live2d_view=MagicMock())

    def test_escape_menu_contains_required_actions(self):
        import inspect
        from ui.live2d_main_window import Live2DMainWindow
        source = inspect.getsource(Live2DMainWindow._build_context_menu)
        for label in ("打开设置", "切回 Sprite", "重置 Live2D 显示参数", "关闭 Maidie"):
            self.assertIn(label, source)

    @patch("ui.live2d_main_window.QMessageBox.information")
    def test_switch_to_sprite_saves_config_and_requires_restart(self, information):
        window = self.window()
        from ui.live2d_main_window import Live2DMainWindow
        self.assertTrue(Live2DMainWindow.switch_to_sprite(window))
        window.controller.apply_settings.assert_called_once_with({"animation_backend": "sprite"})
        self.assertIn("重启", information.call_args.args[2])

    @patch("ui.live2d_main_window.QMessageBox.critical")
    def test_switch_to_sprite_reports_save_failure(self, critical):
        window = self.window()
        window.controller.apply_settings.side_effect = OSError("read only")
        from ui.live2d_main_window import Live2DMainWindow
        self.assertFalse(Live2DMainWindow.switch_to_sprite(window))
        self.assertIn("read only", critical.call_args.args[2])

    @patch("ui.live2d_main_window.QMessageBox.information")
    def test_reset_display_clears_offsets_and_refits(self, _information):
        window = self.window()
        from ui.live2d_main_window import Live2DMainWindow
        self.assertTrue(Live2DMainWindow.reset_live2d_display(window))
        values = window.controller.apply_settings.call_args.args[0]
        self.assertEqual(values["animation_live2d_pet_scale"], 1.0)
        self.assertEqual(values["animation_live2d_pet_offset_x"], 0.0)
        self.assertEqual(values["animation_live2d_pet_offset_y"], 0.0)
        self.assertEqual(values["animation_live2d_pet_align"], "bottom")
        window.live2d_view.reset_display.assert_called_once_with()


class MainWindowCleanupTests(unittest.TestCase):
    def test_shutdown_closes_live2d_server_and_backend_view(self):
        from ui.live2d_main_window import Live2DMainWindow
        from ui.window import PetWindow
        dummy = SimpleNamespace(_shutting_down=False, live2d_view=MagicMock())
        with patch.object(PetWindow, "shutdown") as parent_shutdown:
            Live2DMainWindow.shutdown(dummy)
        dummy.live2d_view.close.assert_called_once_with()
        parent_shutdown.assert_called_once_with(dummy)


if __name__ == "__main__":
    unittest.main()
