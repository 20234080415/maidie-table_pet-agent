from __future__ import annotations

from typing import Any

from animation.live2d_web import Live2DPreviewStatus, resolve_animation_backend
from animation.model_manager import AnimationModel, AnimationModelRegistry


def try_create_live2d_window(
    animation_config: dict[str, Any] | None,
) -> tuple[object | None, dict[str, Any]]:
    """Attempt to create a Live2DPetWindow for experimental preview.

    Returns (window, status_dict).  window is None when Live2D cannot be
    started.  This is an experimental-only function; it does NOT replace
    the main Sprite PetWindow.
    """
    options = dict(animation_config or {})
    resolved, status = resolve_animation_backend(options)
    if resolved != "live2d_web":
        return None, {
            "ok": False, "code": "backend_not_live2d",
            "message": "动画后端不是 live2d_web。",
        }

    registry = AnimationModelRegistry(
        options.get("live2d_models", []), options.get("current_model_id", "")
    )
    model: AnimationModel | None = registry.resolve_current_model()
    if model is None:
        return None, {
            "ok": False, "code": "no_current_model",
            "message": "未选择有效的 Live2D 模型。",
        }

    try:
        from ui.live2d_pet_window import create_live2d_pet_window
    except ImportError:
        return None, {
            "ok": False, "code": "pet_window_import_failed",
            "message": "无法导入 Live2DPetWindow 模块。",
        }

    window, result = create_live2d_pet_window(model, mode="pet")
    if window is None:
        return None, result

    return window, result


def resolve_backend_and_window(
    animation_config: dict[str, Any] | None,
) -> tuple[str, Live2DPreviewStatus, object | None]:
    """Resolve the effective backend and optionally create a Live2D window.

    Always returns "sprite" as the production backend.
    Live2D window is created only for experimental preview use.
    """
    options = dict(animation_config or {})
    backend, status = resolve_animation_backend(options)
    live2d_window: object | None = None

    if backend == "live2d_web":
        live2d_window, _result = try_create_live2d_window(options)

    return "sprite", status, live2d_window
