from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    model_path = Path(args.model).resolve()
    if not model_path.is_file():
        emit({"ok": False, "code": "model_missing", "message": "model3.json 不存在。"})
        return 2

    from PyQt6.QtCore import QTimer, QUrl
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from ui.live2d_preview_dialog import build_load_model_script
    from animation.live2d_web import viewer_root

    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.setWindowTitle(f"Live2D 真实预览 - {args.name}")
    view.resize(720, 760)
    settings = view.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
    last_code = {"value": ""}

    def finish_with(payload: dict[str, Any], exit_code: int = 0) -> None:
        emit(payload)
        if exit_code:
            QTimer.singleShot(50, lambda: app.exit(exit_code))

    def on_state(value: Any) -> None:
        payload = value if isinstance(value, dict) else {}
        code = str(payload.get("code") or "")
        if code and code != last_code["value"]:
            last_code["value"] = code
            emit(payload)
        if code in {"runtime_missing", "model_load_failed"}:
            view.setWindowTitle(f"Live2D 预览失败 - {args.name}")

    def poll() -> None:
        view.page().runJavaScript(
            "window.getPreviewState && window.getPreviewState()", on_state
        )

    def loaded(ok: bool) -> None:
        if not ok:
            finish_with({"ok": False, "code": "viewer_load_failed",
                         "message": "Live2D viewer 页面加载失败。"}, 3)
            return
        emit({"ok": True, "code": "page_ready", "message": "WebEngine 页面已加载。"})
        view.page().runJavaScript(build_load_model_script(model_path))
        timer.start(250)

    view.loadFinished.connect(loaded)
    timer = QTimer()
    timer.timeout.connect(poll)
    view.setUrl(QUrl.fromLocalFile(str((viewer_root() / "index.html").resolve())))
    view.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
