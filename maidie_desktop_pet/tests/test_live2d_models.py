from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

from animation.live2d_web import (Live2DWebPreview, resolve_animation_backend,
                                  runtime_status, viewer_root)
from animation.model_manager import AnimationModelRegistry
from animation.live2d_preview_server import Live2DPreviewServer, open_browser_preview
from core.settings import ConfigStore
from ui.live2d_preview_dialog import build_load_model_script, preview_process_arguments


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
        self.assertIn("Live2D runtime files are missing", status.message)
        self.assertEqual(len(status.details["missing_files"]), 3)

    def test_viewer_exposes_required_javascript_api(self):
        html = (viewer_root() / "index.html").read_text(encoding="utf-8")
        self.assertIn("window.loadModel", html)
        self.assertIn("window.setExpression", html)
        self.assertIn("window.setParameter", html)
        self.assertIn("window.getPreviewState", html)
        self.assertIn("new URLSearchParams(window.location.search).get(\"model\")", html)
        self.assertIn("模型地址：", html)
        self.assertIn("new URL(String(value || \"\").replace", html)
        self.assertIn("Live2D 模型预检失败", html)
        self.assertIn("HTTP 状态：", html)
        self.assertIn("请求地址：", html)
        self.assertIn('id="live2d-canvas-container"', html)
        self.assertIn("适应窗口", html)
        self.assertIn("居中模型", html)
        self.assertIn("重置视图", html)
        self.assertIn("舞台子对象数量：", html)
        self.assertIn("画布尺寸：", html)
        self.assertIn("模型边界：", html)
        self.assertIn("app.stage.addChild(currentModel)", html)
        self.assertIn("function fitModelToViewInternal()", html)
        self.assertIn("function centerModelInternal()", html)
        self.assertIn("currentModel.getLocalBounds()", html)
        self.assertIn("app.renderer.width * fitPadding", html)
        self.assertIn("app.renderer.height * fitPadding", html)
        self.assertIn("fitResizeTimer = setTimeout", html)
        self.assertIn('case "resetView":', html)
        self.assertIn("currentModel.visible = true", html)
        self.assertIn("currentModel.alpha = 1", html)
        self.assertIn("app.ticker.start()", html)
        self.assertIn("模型已加载但不可见", html)
        self.assertIn("Cubism Core 版本：", html)
        self.assertIn("window.loadModel = async function", html)
        self.assertIn("return await loadModelAsync", html)
        self.assertIn("DOMContentLoaded", html)
        self.assertNotIn("version.major <= 4", html)
        self.assertIn("function cubismCoreCompatibility(core)", html)
        self.assertIn("function installCubismCoreCompatibility(core)", html)
        self.assertIn("const originalFromMoc = Model.fromMoc", html)
        self.assertIn("model.getRenderOrders()", html)
        self.assertIn("orders.subarray(0, model.drawables.count)", html)
        self.assertNotIn("return this.drawOrders", html)
        self.assertIn("core.major <= 6", html)
        self.assertIn("compatibility.experimental", html)
        self.assertNotIn("core.major > 4", html)
        self.assertIn("PIXI.ENV.WEBGL_LEGACY", html)
        for label in ("播放随机动作", "切换开心表情",
                      "开始嘴型测试", "启用鼠标跟随"):
            self.assertIn(label, html)
        self.assertIn('name: "ParamAngleX"', html)
        self.assertIn('name: "ParamMouthOpenY"', html)
        self.assertIn("window.playMotion", html)
        self.assertIn("window.playRandomMotion", html)
        self.assertIn("window.clearExpression", html)
        self.assertIn("window.resetParameters", html)
        self.assertIn("window.getModelDiagnostics", html)
        self.assertIn("window.applySemanticState", html)
        self.assertIn("const ACTION_PROFILES", html)
        self.assertIn("语义状态控制", html)
        for state in ("idle", "speaking", "thinking", "confused",
                      "success", "error", "sleepy", "dragged"):
            self.assertIn(f'data-semantic-state="{state}"', html)
        self.assertIn("const profile = ACTION_PROFILES[normalized]", html)
        self.assertIn("confused: {motion_candidates:", html)
        self.assertIn("ParamAngleX: 18", html)
        self.assertIn("ParamAngleY: -12", html)
        self.assertIn("ParamMouthOpenY: 0.25", html)
        self.assertIn("speaking: {motion_candidates:", html)
        self.assertIn("window.startMouthTest()", html)
        for profile in ("headpat", "dragged", "success", "error"):
            self.assertIn(f"{profile}: {{motion_candidates:", html)
        self.assertIn("motion_candidates", html)
        self.assertIn("expression_candidates", html)
        self.assertIn("duration_ms", html)
        self.assertIn("fallback_reason", html)
        self.assertIn("当前语义状态", html)
        self.assertIn("最近应用动作", html)
        self.assertIn("最近应用表情", html)
        self.assertIn("最近参数变化", html)
        self.assertIn("回退原因", html)
        self.assertIn("动作 API 不可用", html)
        self.assertIn("表情 API 不可用", html)
        self.assertIn("参数 API 不可用", html)
        self.assertIn('"not_available"', html)
        self.assertIn("visibleVerdict()", html)
        self.assertIn("await nextRenderFrames(2)", html)
        self.assertLess(html.index("if (!visibleVerdict())"),
                        html.index("window.__maidieLive2DModel = currentModel"))
        self.assertIn("doDrawModel", html)
        self.assertIn("缺少 Live2D 运行库文件", html)
        empty_runtime = self.root / "empty-viewer"
        empty_runtime.mkdir()
        installed, missing = runtime_status(empty_runtime)
        self.assertFalse(installed)
        self.assertTrue(missing)

    def test_windows_model_path_is_passed_as_safe_file_url_json(self):
        script = build_load_model_script(
            Path(r"C:\Users\测试 用户\Live2D\model's demo.model3.json")
        )
        self.assertTrue(script.startswith("window.loadModel("))
        argument = script[len("window.loadModel("):-1]
        decoded = json.loads(argument)
        self.assertTrue(decoded.startswith("file:///"))
        self.assertIn("model's demo.model3.json", decoded)
        self.assertNotIn("\\", decoded)

    def test_preview_uses_crash_isolated_child_process(self):
        model = AnimationModelRegistry().import_model3_json(
            self._model_file("A/a.model3.json"), root=self.root
        )
        arguments = preview_process_arguments(model)
        self.assertEqual(arguments[:2], ["-m", "ui.live2d_preview_process"])
        self.assertIn(str(Path(model.model3_json).resolve()), arguments)
        source = (Path(__file__).parents[1] / "ui" / "live2d_preview_dialog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QProcess", source)
        self.assertNotIn("QtWebEngineWidgets", source)

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

    def test_browser_preview_server_is_loopback_and_maps_only_allowed_roots(self):
        model_path = self._model_file("A/a.model3.json")
        (model_path.parent / "texture.png").write_bytes(b"texture")
        viewer = self.root / "viewer"
        viewer.mkdir()
        (viewer / "index.html").write_text("viewer", encoding="utf-8")
        model = AnimationModelRegistry().import_model3_json(model_path, root=self.root)
        server = Live2DPreviewServer(model, viewer=viewer)
        try:
            url = server.start()
            self.assertEqual(server._httpd.server_address[0], "127.0.0.1")
            self.assertIn("/viewer/index.html?model=/model/", url)
            self.assertEqual(urllib.request.urlopen(
                f"http://127.0.0.1:{server.port}/viewer/index.html"
            ).read(), b"viewer")
            self.assertEqual(urllib.request.urlopen(
                f"http://127.0.0.1:{server.port}/model/{model.id}/texture.png"
            ).read(), b"texture")
            for path in ("/viewer/../outside.txt", "/model/%2e%2e/outside.txt",
                         f"/model/{model.id}/%2e%2e/outside.txt"):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(f"http://127.0.0.1:{server.port}{path}")
                self.assertEqual(caught.exception.code, 403)
        finally:
            server.stop()

    def test_runtime_model_url_and_all_relative_resources_are_served(self):
        model_path = self._model_file("Hibiki/runtime/hibiki.model3.json")
        resources = {
            "hibiki.moc3": b"moc3",
            "textures/texture_00.png": b"texture",
            "motions/idle.motion3.json": b"{}",
            "hibiki.physics3.json": b"{}",
            "expressions/smile.exp3.json": b"{}",
        }
        for relative, content in resources.items():
            resource = model_path.parent / relative
            resource.parent.mkdir(parents=True, exist_ok=True)
            resource.write_bytes(content)
        viewer = self.root / "viewer"
        viewer.mkdir()
        (viewer / "index.html").write_text("viewer", encoding="utf-8")
        model = AnimationModelRegistry().import_model3_json(model_path, root=self.root)
        self.assertEqual(model.metadata["relative_path"], "Hibiki/runtime/hibiki.model3.json")
        server = Live2DPreviewServer(model, viewer=viewer)
        try:
            preview_url = server.start()
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(preview_url).query)
            model_url = query["model"][0]
            self.assertEqual(model_url, f"/model/{model.id}/hibiki.model3.json")
            base = f"http://127.0.0.1:{server.port}/model/{model.id}/"
            self.assertEqual(urllib.request.urlopen(base + "hibiki.model3.json").status, 200)
            for relative, content in resources.items():
                response = urllib.request.urlopen(base + relative)
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), content)
            successful = [entry for entry in server.request_log if entry["status"] == 200]
            self.assertTrue(all(entry["allowed_root"] == str(model_path.parent.resolve())
                                for entry in successful))
        finally:
            server.stop()

    def test_missing_resource_error_contains_http_mapping_diagnostics(self):
        model_path = self._model_file("Hibiki/runtime/hibiki.model3.json")
        viewer = self.root / "viewer"
        viewer.mkdir()
        (viewer / "index.html").write_text("viewer", encoding="utf-8")
        model = AnimationModelRegistry().import_model3_json(model_path, root=self.root)
        server = Live2DPreviewServer(model, viewer=viewer)
        try:
            server.start()
            url = (f"http://127.0.0.1:{server.port}/model/{model.id}/"
                   "textures/missing.png")
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(url)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(payload["status"], 404)
            self.assertEqual(payload["request_path"],
                             f"/model/{model.id}/textures/missing.png")
            self.assertEqual(payload["resolved_path"],
                             str((model_path.parent / "textures/missing.png").resolve()))
            self.assertEqual(payload["allowed_root"], str(model_path.parent.resolve()))
        finally:
            server.stop()

    def test_deleted_model_entry_returns_structured_error(self):
        model_path = self._model_file("A/a.model3.json")
        viewer = self.root / "viewer"
        viewer.mkdir()
        (viewer / "index.html").write_text("viewer", encoding="utf-8")
        model = AnimationModelRegistry().import_model3_json(model_path, root=self.root)
        server = Live2DPreviewServer(model, viewer=viewer)
        try:
            server.start()
            model_path.unlink()
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{server.port}/model/{model.id}/{model_path.name}"
                )
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(payload["code"], "model3_json_missing")
        finally:
            server.stop()

    def test_missing_model_entry_fails_with_structured_error(self):
        model_path = self._model_file("A/a.model3.json")
        model = AnimationModelRegistry().import_model3_json(model_path, root=self.root)
        model_path.unlink()
        server, result = open_browser_preview(model)
        self.assertIsNone(server)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "model3_json_missing")

    def test_browser_preview_does_not_change_backend(self):
        model = AnimationModelRegistry().import_model3_json(
            self._model_file("A/a.model3.json"), root=self.root
        )
        with patch("animation.live2d_preview_server.viewer_root") as root, \
                patch("animation.live2d_preview_server.webbrowser.open") as browser:
            viewer = self.root / "viewer"
            viewer.mkdir()
            (viewer / "index.html").write_text("viewer", encoding="utf-8")
            root.return_value = viewer
            server, result = open_browser_preview(model)
            self.assertTrue(result["ok"])
            self.assertEqual(model.backend, "live2d_web")
            self.assertNotIn("backend", result)
            if server is not None:
                server.stop()


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
            "live2d_pet_scale": 1.0, "live2d_pet_offset_x": 0.0,
            "live2d_pet_offset_y": 0.0, "live2d_pet_align": "bottom",
            "live2d_fit_padding": 0.88,
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
