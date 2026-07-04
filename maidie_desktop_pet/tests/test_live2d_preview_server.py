from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from animation.live2d_preview_server import Live2DPreviewServer
from animation.model_manager import AnimationModelRegistry


class Live2DPreviewServerCommandTests(unittest.TestCase):
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

    def _create_server(self):
        return Live2DPreviewServer(self.model, viewer=self.viewer)

    def test_start_generates_session_id(self):
        server = self._create_server()
        try:
            url = server.start()
            self.assertTrue(server.session_id)
            self.assertEqual(len(server.session_id), 32)
        finally:
            server.stop()

    def test_viewer_url_contains_session_parameter(self):
        server = self._create_server()
        try:
            url = server.start()
            self.assertIn("session=" + server.session_id, url)
            self.assertIn("/viewer/index.html?model=/model/", url)
        finally:
            server.stop()

    def test_enqueue_and_drain_commands_via_api(self):
        server = self._create_server()
        try:
            server.start()
            self.assertTrue(server.enqueue_command(server.session_id, {
                "command": "applySemanticState", "args": ["confused", 1.2],
            }))
            self.assertTrue(server.enqueue_command(server.session_id, {
                "command": "setParameter", "args": ["ParamAngleX", 15],
            }))
            api_url = (
                f"http://127.0.0.1:{server.port}"
                f"/api/commands?session={server.session_id}"
            )
            response = urllib.request.urlopen(api_url)
            payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(len(payload["commands"]), 2)
            self.assertEqual(payload["commands"][0]["command"], "applySemanticState")
            self.assertEqual(payload["commands"][0]["args"], ["confused", 1.2])
            self.assertEqual(payload["commands"][1]["command"], "setParameter")
            self.assertEqual(payload["commands"][1]["args"], ["ParamAngleX", 15])
        finally:
            server.stop()

    def test_drain_clears_queue_second_get_returns_empty(self):
        server = self._create_server()
        try:
            server.start()
            server.enqueue_command(server.session_id, {
                "command": "applySemanticState", "args": ["idle"],
            })
            api_url = (
                f"http://127.0.0.1:{server.port}"
                f"/api/commands?session={server.session_id}"
            )
            first = json.loads(urllib.request.urlopen(api_url).read().decode("utf-8"))
            self.assertEqual(len(first["commands"]), 1)
            second = json.loads(urllib.request.urlopen(api_url).read().decode("utf-8"))
            self.assertEqual(len(second["commands"]), 0)
        finally:
            server.stop()

    def test_unknown_session_returns_structured_error(self):
        server = self._create_server()
        try:
            server.start()
            api_url = (
                f"http://127.0.0.1:{server.port}"
                f"/api/commands?session=does-not-exist"
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(api_url)
            self.assertEqual(caught.exception.code, 404)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["code"], "unknown_session")
        finally:
            server.stop()

    def test_missing_session_parameter_returns_error(self):
        server = self._create_server()
        try:
            server.start()
            api_url = f"http://127.0.0.1:{server.port}/api/commands"
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(api_url)
            self.assertEqual(caught.exception.code, 400)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["code"], "missing_session")
        finally:
            server.stop()

    def test_api_commands_is_not_a_file_path(self):
        server = self._create_server()
        try:
            server.start()
            api_url = f"http://127.0.0.1:{server.port}/api/commands?session=../config"
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(api_url)
            self.assertEqual(caught.exception.code, 404)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(payload["code"], "unknown_session")
        finally:
            server.stop()

    def test_api_path_is_not_served_as_file(self):
        server = self._create_server()
        try:
            server.start()
            api_url = f"http://127.0.0.1:{server.port}/api/"
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(api_url)
            self.assertEqual(caught.exception.code, 403)
        finally:
            server.stop()

    def test_enqueue_command_returns_false_for_unknown_session(self):
        server = self._create_server()
        try:
            server.start()
            self.assertFalse(
                server.enqueue_command("bad-session", {"command": "reset"})
            )
        finally:
            server.stop()

    def test_command_queue_maxlen_discards_oldest(self):
        server = self._create_server()
        try:
            server.start()
            for index in range(server.COMMAND_QUEUE_MAXLEN + 7):
                self.assertTrue(server.enqueue_command(
                    server.session_id, {"command": "test", "args": [index]}
                ))
            commands = server.drain_commands(server.session_id)
            self.assertEqual(len(commands), server.COMMAND_QUEUE_MAXLEN)
            self.assertEqual(commands[0]["args"], [7])
        finally:
            server.stop()

    def test_stop_clears_queues_and_is_idempotent(self):
        server = self._create_server()
        server.start()
        session_id = server.session_id
        server.enqueue_command(session_id, {"command": "reset"})
        server.stop()
        self.assertFalse(server.has_command_session(session_id))
        self.assertEqual(server.drain_commands(session_id), [])
        server.stop()

    def test_default_animation_backend_is_sprite(self):
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

    def test_viewer_html_contains_command_polling(self):
        from animation.live2d_web import viewer_root
        html = (viewer_root() / "index.html").read_text(encoding="utf-8")
        self.assertIn("startCommandPolling", html)
        self.assertIn("/api/commands?session=", html)
        self.assertIn("executeRemoteCommand", html)
        self.assertIn("setInterval(pollCommands, 200)", html)
        self.assertIn("if (window.__maidieCommandPollTimer) return", html)
        self.assertIn("if (isPolling) return", html)
        self.assertIn("finally", html)
        for cmd in ("applySemanticState", "playMotion", "setExpression",
                     "setParameter", "startMouthTest", "stopMouthTest",
                     "setMouseFollow", "reset"):
            self.assertIn(f'case "{cmd}":', html)

    def test_browser_preview_does_not_replace_main_sprite(self):
        model = AnimationModelRegistry().import_model3_json(
            self.root / "A" / "a.model3.json", root=self.root
        )
        with patch("animation.live2d_preview_server.viewer_root") as root_mock, \
                patch("animation.live2d_preview_server.webbrowser.open") as browser:
            root_mock.return_value = self.viewer
            from animation.live2d_preview_server import open_browser_preview
            server, result = open_browser_preview(model)
            self.assertTrue(result["ok"])
            if server is not None:
                server.stop()
            from animation.live2d_web import resolve_animation_backend
            backend, status = resolve_animation_backend({"backend": "sprite"})
            self.assertEqual(backend, "sprite")


if __name__ == "__main__":
    unittest.main()
