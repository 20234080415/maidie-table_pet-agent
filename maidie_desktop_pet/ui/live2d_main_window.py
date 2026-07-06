from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt

from animation.model_manager import AnimationModel
from ui.live2d_pet_window import create_live2d_pet_window
from ui.window import PetWindow


class Live2DMainWindow(PetWindow):
    """Production window shell that reuses PetWindow UI with Live2D rendering."""

    def __init__(self, live2d_view, controller, assets_dir: Path,
                 options: dict[str, Any] | None = None, confirmation_broker=None,
                 fence_options: dict[str, Any] | None = None) -> None:
        super().__init__(controller, assets_dir, options, confirmation_broker, fence_options)
        self.live2d_view = live2d_view
        self.live2d_view.setParent(self)
        self.live2d_view.setWindowFlags(Qt.WindowType.Widget)
        self.layout().replaceWidget(self.character, self.live2d_view)
        self.character.hide()
        self.live2d_view.show()
        controller.animation_changed.connect(self.apply_live2d_state)
        controller.state_changed.connect(self.apply_live2d_state)
        controller.emotion_changed.connect(self.apply_live2d_state)
        self.apply_live2d_state("idle")

    def apply_live2d_state(self, state: str) -> dict[str, Any]:
        backend = self.live2d_view.current_backend()
        if backend is None:
            return {"ok": False, "error": "Live2D backend is unavailable."}
        return backend.apply_state(state)

    def shutdown(self) -> None:
        if not self._shutting_down:
            self.live2d_view.close()
        PetWindow.shutdown(self)


def create_live2d_main_window(
    model: AnimationModel | None, controller, assets_dir: Path,
    window_options: dict[str, Any] | None = None, confirmation_broker=None,
    fence_options: dict[str, Any] | None = None,
    animation_options: dict[str, Any] | None = None,
) -> tuple[Live2DMainWindow | None, dict[str, Any]]:
    options = dict(animation_options or {})
    view, result = create_live2d_pet_window(
        model, mode="pet",
        pet_scale=float(options.get("pet_scale", 0.0) or 0.0),
        pet_offset_x=float(options.get("pet_offset_x", 0.0) or 0.0),
        pet_offset_y=float(options.get("pet_offset_y", 0.0) or 0.0),
        pet_align=str(options.get("pet_align", "bottom") or "bottom"),
        pet_bg=str(options.get("pet_bg", "transparent") or "transparent"),
    )
    if view is None:
        return None, result
    try:
        window = Live2DMainWindow(
            view, controller, assets_dir, window_options,
            confirmation_broker, fence_options,
        )
    except Exception as exc:
        view.close()
        return None, {
            "ok": False, "code": "main_window_creation_failed",
            "message": f"创建 Live2D 主桌宠窗口失败：{exc}", "error": str(exc),
        }
    return window, {
        "ok": True, "code": "live2d_main_window_created",
        "message": f"Live2D 主桌宠已启动：{model.name if model else ''}",
    }
