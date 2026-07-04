from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from animation.model_manager import AnimationModel, AnimationModelRegistry


RUNTIME_MESSAGE = (
    "Live2D Web Runtime is not installed. Please place runtime files under "
    "assets/live2d/viewer/vendor/ or configure runtime path."
)
RUNTIME_FILES = (
    "pixi.min.js",
    "live2dcubismcore.min.js",
    "cubism4.min.js",
)


@dataclass(frozen=True)
class Live2DPreviewStatus:
    available: bool
    message: str
    model_name: str = ""
    model3_json: str = ""
    code: str = "ok"
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.available,
            "code": self.code,
            "message": self.message,
            "model_name": self.model_name,
            "model3_json": self.model3_json,
            "details": dict(self.details or {}),
        }


def webengine_available() -> bool:
    """Check optional WebEngine without importing it during application startup."""
    try:
        return find_spec("PyQt6.QtWebEngineWidgets") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def viewer_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "live2d" / "viewer"


def runtime_status(root: str | Path | None = None) -> tuple[bool, list[str]]:
    vendor = Path(root or viewer_root()) / "vendor"
    missing = [name for name in RUNTIME_FILES if not (vendor / name).is_file()]
    return not missing, missing


class Live2DWebPreview:
    """Capability validation for the optional, isolated Live2D preview window."""

    def inspect(self, model: AnimationModel | None, *, require_runtime: bool = False,
                root: str | Path | None = None) -> Live2DPreviewStatus:
        if model is None:
            return Live2DPreviewStatus(
                False, "未选择有效的 Live2D 模型。", code="model_not_selected"
            )
        model_path = Path(model.model3_json)
        if not model_path.is_file():
            return Live2DPreviewStatus(
                False, "模型入口不存在。", model.name, model.model3_json,
                "model_missing", {"path": model.model3_json},
            )
        if not webengine_available():
            return Live2DPreviewStatus(
                False, "未安装 PyQt6-WebEngine，无法创建真实 Live2D 预览。",
                model.name, model.model3_json, "webengine_missing",
            )
        root_path = Path(root or viewer_root())
        index = root_path / "index.html"
        if not index.is_file():
            return Live2DPreviewStatus(
                False, "Live2D viewer/index.html 不存在。", model.name,
                model.model3_json, "viewer_missing", {"path": str(index)},
            )
        installed, missing = runtime_status(root_path)
        if require_runtime and not installed:
            return Live2DPreviewStatus(
                False, RUNTIME_MESSAGE, model.name, model.model3_json,
                "runtime_missing", {"missing_files": missing},
            )
        message = ("Live2D 真实预览组件可用。" if installed else RUNTIME_MESSAGE)
        return Live2DPreviewStatus(
            installed, message, model.name, model.model3_json,
            "ok" if installed else "runtime_missing", {"missing_files": missing},
        )


def resolve_animation_backend(animation: dict | None) -> tuple[str, Live2DPreviewStatus]:
    """Return a safe runtime backend without mutating persistent configuration."""
    options = dict(animation or {})
    if options.get("backend") != "live2d_web":
        return "sprite", Live2DPreviewStatus(True, "使用 Sprite 动画后端。")
    registry = AnimationModelRegistry(
        options.get("live2d_models", []), options.get("current_model_id", "")
    )
    status = Live2DWebPreview().inspect(registry.resolve_current_model(), require_runtime=True)
    return ("live2d_web" if status.available else "sprite"), status
