from __future__ import annotations

import json
import mimetypes
import threading
import uuid
import webbrowser
from collections import deque
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from animation.live2d_web import viewer_root
from animation.model_manager import AnimationModel


class Live2DPreviewServer:
    """Loopback-only HTTP server for one Live2D model and the local viewer."""

    host = "127.0.0.1"

    def __init__(self, model: AnimationModel, *, viewer: str | Path | None = None,
                 lifetime_seconds: float = 1800) -> None:
        self.model = model
        self.viewer_root = Path(viewer or viewer_root()).expanduser().resolve()
        self.model_entry = Path(model.model3_json).expanduser().resolve()
        self.model_root = self.model_entry.parent
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lifetime_seconds = lifetime_seconds
        self._stop_timer: threading.Timer | None = None
        self.request_log: deque[dict[str, Any]] = deque(maxlen=200)
        self._session_id: str = ""
        self._command_queues: dict[str, deque[dict[str, Any]]] = {}

    @property
    def port(self) -> int:
        if self._httpd is None:
            raise RuntimeError("Live2D preview server has not started")
        return int(self._httpd.server_address[1])

    def start(self) -> str:
        if not self.model_entry.is_file():
            raise FileNotFoundError(json.dumps({
                "ok": False,
                "code": "model3_json_missing",
                "message": "Live2D model3_json 不存在。",
                "model3_json": str(self.model_entry),
            }, ensure_ascii=False))
        if not self.viewer_root.joinpath("index.html").is_file():
            raise FileNotFoundError("Live2D viewer/index.html 不存在。")
        if self._httpd is None:
            self._session_id = uuid.uuid4().hex
            self._command_queues[self._session_id] = deque()
            handler = partial(_PreviewRequestHandler, preview=self)
            self._httpd = ThreadingHTTPServer((self.host, 0), handler)
            self._httpd.daemon_threads = True
            self._thread = threading.Thread(
                target=self._httpd.serve_forever,
                name="live2d-preview-http",
                daemon=True,
            )
            self._thread.start()
            if self._lifetime_seconds > 0:
                self._stop_timer = threading.Timer(self._lifetime_seconds, self.stop)
                self._stop_timer.daemon = True
                self._stop_timer.start()
        return self.viewer_url()

    @property
    def session_id(self) -> str:
        return self._session_id

    def viewer_url(self, mode: str = "preview") -> str:
        model_id = quote(self.model.id, safe="")
        filename = quote(self.model_entry.name, safe="")
        model_url = f"/model/{model_id}/{filename}"
        url = (
            f"http://{self.host}:{self.port}/viewer/index.html"
            f"?model={quote(model_url, safe='/')}"
        )
        if self._session_id:
            url += f"&session={self._session_id}"
        if mode:
            url += f"&mode={mode}"
        return url

    def enqueue_command(self, session_id: str, command: dict[str, Any]) -> bool:
        if session_id not in self._command_queues:
            return False
        self._command_queues[session_id].append(dict(command))
        return True

    def drain_commands(self, session_id: str) -> list[dict[str, Any]]:
        queue = self._command_queues.get(session_id)
        if queue is None:
            return []
        commands = list(queue)
        queue.clear()
        return commands

    def stop(self) -> None:
        timer, self._stop_timer = self._stop_timer, None
        if timer is not None and timer is not threading.current_thread():
            timer.cancel()
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._command_queues.clear()

    def resolve_request_path(self, request_path: str) -> Path | None:
        path = unquote(urlsplit(request_path).path)
        if "\\" in path or "\x00" in path:
            return None
        parts = PurePosixPath(path).parts
        root: Path
        relative: tuple[str, ...]
        if len(parts) >= 3 and parts[:2] == ("/", "viewer"):
            root, relative = self.viewer_root, parts[2:]
        elif (len(parts) >= 4 and parts[:2] == ("/", "model")
              and parts[2] == self.model.id):
            root, relative = self.model_root, parts[3:]
        else:
            return None
        if not relative or any(part in {"", ".", ".."} for part in relative):
            return None
        candidate = root.joinpath(*relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    def allowed_root_for(self, request_path: str) -> Path | None:
        path = unquote(urlsplit(request_path).path)
        parts = PurePosixPath(path).parts
        if len(parts) >= 2 and parts[:2] == ("/", "viewer"):
            return self.viewer_root
        if (len(parts) >= 3 and parts[:2] == ("/", "model")
                and parts[2] == self.model.id):
            return self.model_root
        return None

    def record_request(self, request_path: str, target: Path | None,
                       allowed_root: Path | None, status: int) -> dict[str, Any]:
        entry = {
            "request_path": urlsplit(request_path).path,
            "resolved_path": str(target) if target is not None else None,
            "allowed_root": str(allowed_root) if allowed_root is not None else None,
            "status": status,
        }
        self.request_log.append(entry)
        return entry


class _PreviewRequestHandler(BaseHTTPRequestHandler):
    server_version = "MaidieLive2DPreview/1.0"

    def __init__(self, *args: Any, preview: Live2DPreviewServer, **kwargs: Any) -> None:
        self.preview = preview
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        if self._handle_api():
            return
        self._serve(send_body=True)

    def do_HEAD(self) -> None:
        if self._handle_api():
            return
        self._serve(send_body=False)

    def _handle_api(self) -> bool:
        parsed = urlsplit(self.path)
        if parsed.path != "/api/commands":
            return False
        query = parse_qs(parsed.query)
        session_id = (query.get("session", [""])[0]).strip()
        if not session_id:
            self._error(400, "missing_session", "session 参数缺失。", True,
                        {"request_path": parsed.path})
            return True
        if session_id not in self.preview._command_queues:
            self._error(404, "unknown_session", "未知的 command session。", True,
                        {"request_path": parsed.path, "session_id": session_id})
            return True
        commands = self.preview.drain_commands(session_id)
        data = json.dumps({"ok": True, "commands": commands}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return True

    def _serve(self, *, send_body: bool) -> None:
        target = self.preview.resolve_request_path(self.path)
        allowed_root = self.preview.allowed_root_for(self.path)
        if target is None:
            details = self.preview.record_request(self.path, None, allowed_root, 403)
            self._error(403, "path_forbidden", "请求路径不在 Live2D 预览范围内。",
                        send_body, details)
            return
        if not target.is_file():
            code = "model3_json_missing" if target == self.preview.model_entry else "file_not_found"
            details = self.preview.record_request(self.path, target, allowed_root, 404)
            self._error(404, code, "请求的 Live2D 文件不存在。", send_body, details)
            return
        try:
            data = target.read_bytes()
        except OSError as exc:
            details = self.preview.record_request(self.path, target, allowed_root, 500)
            self._error(500, "file_read_failed", str(exc), send_body, details)
            return
        self.preview.record_request(self.path, target, allowed_root, 200)
        self.send_response(200)
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _error(self, status: int, code: str, message: str, send_body: bool,
               details: dict[str, Any]) -> None:
        data = json.dumps({"ok": False, "code": code, "message": message, **details},
                          ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def log_message(self, _format: str, *args: Any) -> None:
        return


def open_browser_preview(model: AnimationModel) -> tuple[Live2DPreviewServer | None, dict[str, Any]]:
    """Start the server and ask the default browser to open it off the GUI thread."""
    server = Live2DPreviewServer(model)
    try:
        url = server.start()
    except FileNotFoundError as exc:
        try:
            payload = json.loads(str(exc))
        except json.JSONDecodeError:
            payload = {"ok": False, "code": "browser_preview_failed", "message": str(exc)}
        return None, payload
    except (OSError, ValueError) as exc:
        return None, {"ok": False, "code": "browser_preview_failed", "message": str(exc)}

    def _open() -> None:
        webbrowser.open(url)

    threading.Thread(target=_open, name="live2d-preview-browser", daemon=True).start()
    return server, {
        "ok": True,
        "code": "browser_preview_opened",
        "message": "已使用系统默认浏览器打开 Live2D 预览。",
        "url": url,
    }
