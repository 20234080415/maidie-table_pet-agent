from __future__ import annotations

from pathlib import Path
from time import monotonic

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QLabel, QSizePolicy

from animation.atlas import AtlasAnimationEngine


class HatchPetSprite(QLabel):
    """Scalable view for an animation backend; contains no behavior rules."""

    def __init__(self, atlas_path: Path, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.engine = AtlasAnimationEngine(atlas_path, self)
        self.engine.frame_changed.connect(self._receive_frame)
        self._frame = self.engine.current_frame()
        self._gaze_x = 0.0
        self._gaze_y = 0.0
        self._transition_from: QPixmap | None = None
        self._transition_from_scale = 1.0
        self._transition_progress = 1.0
        self._transition_started = 0.0
        self._transition_duration = 0.16
        self._transition_timer = QTimer(self)
        self._transition_timer.setInterval(16)
        self._transition_timer.timeout.connect(self._advance_transition)
        self._render()

    def set_animation(self, state: str) -> None:
        if state == self.engine.animation:
            return
        self._transition_from = self._frame
        self._transition_from_scale = self.engine.render_scale
        self._transition_progress = 0.0
        self._transition_started = monotonic()
        self._transition_timer.start()
        self.engine.set_animation(state)

    def _receive_frame(self, frame: QPixmap) -> None:
        self._frame = frame
        self._render()

    def _render(self) -> None:
        if self.width() < 1 or self.height() < 1:
            return
        # Always draw from the untouched 192x208 source frame. The output
        # canvas follows the monitor's physical pixel ratio, so shrinking and
        # re-enlarging never reuses a low-resolution intermediate pixmap.
        dpr = max(1.0, self.devicePixelRatioF())
        canvas = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
        canvas.setDevicePixelRatio(dpr)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._gaze_x * 0.55 if self.engine.animation == "idle" else 0.0)
        painter.translate(-self.width() / 2, -self.height() / 2)
        render_frame = self._eye_tracked_frame()
        if self._transition_from is not None and self._transition_progress < 1.0:
            self._draw_frame(
                painter,
                self._transition_from,
                self._transition_from_scale,
                1.0 - self._transition_progress,
            )
            self._draw_frame(
                painter,
                render_frame,
                self.engine.render_scale,
                self._transition_progress,
            )
        else:
            self._draw_frame(painter, render_frame, self.engine.render_scale, 1.0)
        painter.end()
        self.setPixmap(canvas)

    def _draw_frame(
        self, painter: QPainter, frame: QPixmap, render_scale: float, opacity: float
    ) -> None:
        painter.save()
        painter.setOpacity(max(0.0, min(1.0, opacity)))
        painter.drawPixmap(
            self._source_draw_rect(frame, render_scale),
            frame,
            QRectF(frame.rect()),
        )
        painter.restore()

    def _source_draw_rect(
        self, frame: QPixmap | None = None, render_scale: float | None = None
    ) -> QRectF:
        frame = frame or self._frame
        scale = self.engine.render_scale if render_scale is None else render_scale
        available_w = self.width() * 0.94 * scale
        available_h = self.height() * 0.94 * scale
        source_ratio = frame.width() / frame.height()
        if available_w / available_h > source_ratio:
            draw_h = available_h
            draw_w = draw_h * source_ratio
        else:
            draw_w = available_w
            draw_h = draw_w / source_ratio
        return QRectF(
            (self.width() - draw_w) / 2,
            (self.height() - draw_h) / 2,
            draw_w,
            draw_h,
        )

    def _advance_transition(self) -> None:
        elapsed = monotonic() - self._transition_started
        self._transition_progress = min(1.0, elapsed / self._transition_duration)
        if self._transition_progress >= 1.0:
            self._transition_timer.stop()
            self._transition_from = None
        self._render()

    def head_hit_test(self, point: QPoint) -> bool:
        """Scale-aware hitbox for the visible chibi head."""
        return self.interaction_region(point) == "head"

    def interaction_region(self, point: QPoint) -> str:
        """Return a scale-aware semantic hit region for pointer interactions."""
        rect = self._source_draw_rect()
        if not rect.contains(point.x(), point.y()):
            return "outside"
        source_x = (point.x() - rect.x()) / rect.width() * 192
        source_y = (point.y() - rect.y()) / rect.height() * 208
        if 44 <= source_x <= 148 and 22 <= source_y <= 58:
            return "head"
        if 48 <= source_x <= 144 and 58 < source_y <= 106:
            return "face"
        return "body"

    def set_gaze(self, x: float, y: float) -> None:
        self._gaze_x = max(-1.0, min(1.0, x))
        self._gaze_y = max(-1.0, min(1.0, y))
        self._render()

    def _eye_tracked_frame(self) -> QPixmap:
        """Shift the original idle irises by a few source pixels."""
        if self.engine.animation != "idle":
            return self._frame
        dx = round(self._gaze_x * 2.0)
        dy = round(self._gaze_y * 1.25)
        if dx == 0 and dy == 0:
            return self._frame

        original = self._frame.toImage()
        image = original.copy()
        eye_regions = ((70, 64, 90, 85), (101, 64, 121, 85))
        for left, top, right, bottom in eye_regions:
            selected: list[tuple[int, int]] = []
            for py in range(top, bottom):
                for px in range(left, right):
                    color = original.pixelColor(px, py)
                    if (
                        color.alpha() > 0
                        and color.blue() > 100
                        and color.blue() > color.green() * 1.2
                        and color.red() > color.green() * 1.2
                    ):
                        selected.append((px, py))
            # Blink frames contain no purple iris and remain untouched.
            if len(selected) < 20:
                continue
            targets = {
                (px + dx, py + dy)
                for px, py in selected
                if left <= px + dx < right and top <= py + dy < bottom
            }
            for px, py in selected:
                if (px, py) not in targets:
                    sample_x = max(left, min(right - 1, px - dx))
                    sample_y = max(top, min(bottom - 1, py - dy))
                    image.setPixelColor(px, py, original.pixelColor(sample_x, sample_y))
            for px, py in selected:
                target_x, target_y = px + dx, py + dy
                if left <= target_x < right and top <= target_y < bottom:
                    image.setPixelColor(target_x, target_y, original.pixelColor(px, py))
        return QPixmap.fromImage(image)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render()
