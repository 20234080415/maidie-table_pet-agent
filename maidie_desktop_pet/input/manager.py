from __future__ import annotations

from PyQt6.QtCore import QObject, QPoint, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor


class InputManager(QObject):
    """Continuously observes global cursor proximity and emits semantic input."""

    cursor_moved = pyqtSignal(int, int)
    cursor_near = pyqtSignal(bool)
    cursor_hover = pyqtSignal(bool)

    def __init__(self, geometry_provider, interval_ms: int = 80, near_radius: int = 150):
        super().__init__()
        self._geometry_provider = geometry_provider
        self._near_radius = near_radius
        self._last_pos: QPoint | None = None
        self._near = False
        self._hover = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(interval_ms)

    def _poll(self) -> None:
        position = QCursor.pos()
        if position != self._last_pos:
            self._last_pos = position
            self.cursor_moved.emit(position.x(), position.y())

        rect: QRect = self._geometry_provider()
        hover = rect.contains(position)
        expanded = rect.adjusted(-self._near_radius, -self._near_radius, self._near_radius, self._near_radius)
        near = expanded.contains(position) and not hover
        if hover != self._hover:
            self._hover = hover
            self.cursor_hover.emit(hover)
        if near != self._near:
            self._near = near
            self.cursor_near.emit(near)
