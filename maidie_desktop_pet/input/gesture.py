from __future__ import annotations

from PyQt6.QtCore import QPoint


class PetGestureRecognizer:
    """Distinguishes horizontal head stroking from ordinary window dragging."""

    def __init__(self) -> None:
        self.reset()

    def begin(self, region: str, point: QPoint, pet_width: int) -> None:
        self.region = region
        self.origin = QPoint(point)
        self.last = QPoint(point)
        self.pet_width = max(1, pet_width)
        self.total_horizontal = 0.0
        self.last_direction = 0
        self.reversals = 0
        self.consumed = False

    def update(self, point: QPoint) -> str:
        if self.origin is None or self.last is None:
            return "drag"
        if self.region != "head":
            return "drag"
        step_x = point.x() - self.last.x()
        self.total_horizontal += abs(step_x)
        direction = 1 if step_x > 1 else -1 if step_x < -1 else 0
        if direction and self.last_direction and direction != self.last_direction:
            self.reversals += 1
        if direction:
            self.last_direction = direction
        self.last = QPoint(point)

        total_x = point.x() - self.origin.x()
        total_y = point.y() - self.origin.y()
        if abs(total_y) > max(16, self.pet_width * 0.12):
            return "drag"
        if abs(total_x) > max(42, self.pet_width * 0.30) and self.reversals == 0:
            return "drag"
        threshold = max(24, self.pet_width * 0.18)
        if self.reversals >= 1 and self.total_horizontal >= threshold:
            self.consumed = True
            return "headpat"
        return "pending"

    def reset(self) -> None:
        self.region = "outside"
        self.origin: QPoint | None = None
        self.last: QPoint | None = None
        self.pet_width = 1
        self.total_horizontal = 0.0
        self.last_direction = 0
        self.reversals = 0
        self.consumed = False
