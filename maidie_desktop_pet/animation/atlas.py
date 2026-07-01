from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap

from animation.base import AnimationBackend


class AtlasAnimationEngine(QObject, AnimationBackend):
    """Timed hatch-pet atlas backend; resizing never alters playback speed."""

    frame_changed = pyqtSignal(QPixmap)
    animation_finished = pyqtSignal(str)
    CELL_WIDTH = 192
    CELL_HEIGHT = 208
    # name -> row, frame count, interval, row-level visual scale correction
    ANIMATIONS = {
        "idle": (0, 6, 190, 1.0),
        "thinking": (7, 6, 170, 1.0),
        "talking": (3, 4, 180, 1.0),
        "happy": (4, 5, 135, 1.30),
        "reacting": (3, 4, 180, 1.0),
        "sleeping": (0, 6, 420, 1.0),
        "walk-right": (1, 8, 185, 1.0),
        "walk-left": (2, 8, 185, 1.0),
        "run-right": (1, 8, 95, 1.0),
        "run-left": (2, 8, 95, 1.0),
        "waiting": (6, 6, 200, 1.0),
        "review": (8, 6, 190, 1.0),
        "failed": (5, 8, 210, 1.0),
    }

    def __init__(self, atlas_path: Path, parent=None):
        super().__init__(parent)
        self._atlas = QPixmap(str(atlas_path))
        if self._atlas.isNull():
            raise RuntimeError(f"Cannot load Maidie atlas: {atlas_path}")
        expected = (self.CELL_WIDTH * 8, self.CELL_HEIGHT * 9)
        actual = (self._atlas.width(), self._atlas.height())
        if actual != expected:
            raise ValueError(f"Invalid hatch-pet atlas size: {actual}, expected {expected}")
        self._row = 0
        self._count = 6
        self._frame = 0
        self._name = "idle"
        self._render_scale = 1.0
        self._sheet = self._atlas
        self._loop = True
        self._external = self._load_external_actions(atlas_path.parent / "actions" / "actions.json")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self.set_animation("idle")

    @property
    def animation(self) -> str:
        return self._name

    @property
    def interval(self) -> int:
        return self._timer.interval()

    @property
    def render_scale(self) -> float:
        return self._render_scale

    def set_animation(self, name: str) -> None:
        external = self._external.get(name)
        if external:
            row, count, interval, render_scale = 0, external[1], external[2], external[3]
            sheet = external[0]
            loop = external[4]
        else:
            row, count, interval, render_scale = self.ANIMATIONS.get(name, self.ANIMATIONS["idle"])
            sheet = self._atlas
            loop = True
        if name == self._name and self._timer.isActive():
            return
        self._name = name
        self._row = row
        self._count = count
        self._frame = 0
        self._render_scale = render_scale
        self._sheet = sheet
        self._loop = loop
        self._timer.start(interval)
        self._emit_frame()

    def _advance(self) -> None:
        if self._frame + 1 >= self._count and not self._loop:
            self._timer.stop()
            self.animation_finished.emit(self._name)
            return
        self._frame = (self._frame + 1) % self._count
        self._emit_frame()

    def _emit_frame(self) -> None:
        self.frame_changed.emit(self._sheet.copy(
            self._frame * self.CELL_WIDTH,
            self._row * self.CELL_HEIGHT,
            self.CELL_WIDTH,
            self.CELL_HEIGHT,
        ))

    def current_frame(self) -> QPixmap:
        return self._sheet.copy(
            self._frame * self.CELL_WIDTH,
            self._row * self.CELL_HEIGHT,
            self.CELL_WIDTH,
            self.CELL_HEIGHT,
        )

    def stop(self) -> None:
        self._timer.stop()

    def _load_external_actions(
        self, manifest_path: Path
    ) -> dict[str, tuple[QPixmap, int, int, float, bool]]:
        if not manifest_path.exists():
            return {}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        actions: dict[str, tuple[QPixmap, int, int, float, bool]] = {}
        for name, values in manifest.items():
            sheet = QPixmap(str(manifest_path.parent / values["file"]))
            frames = int(values["frames"])
            if sheet.isNull() or sheet.width() != self.CELL_WIDTH * frames or sheet.height() != self.CELL_HEIGHT:
                continue
            actions[name] = (
                sheet,
                frames,
                int(values.get("interval", 150)),
                float(values.get("render_scale", 1.0)),
                bool(values.get("loop", False)),
            )
        return actions
