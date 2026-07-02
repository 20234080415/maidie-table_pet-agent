from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen, QRegion
from PyQt6.QtWidgets import QWidget

from core.movement import Bounds


class FenceOverlayWindow(QWidget):
    """Non-activating fence frame with a click-through center."""

    rect_change_requested = pyqtSignal(object)
    _HIT_WIDTH = 8
    _MOVE_HANDLE_HALF_WIDTH = 30
    _MIN_SIZE = 80

    def __init__(self) -> None:
        super().__init__(None)
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("")
        self.setMouseTracking(True)
        self._drag_mode = ""
        self._drag_origin = QPoint()
        self._drag_geometry = QRect()

    def update_rect(self, rect: Bounds | QRect | tuple[float, float, float, float]) -> None:
        """Apply global fence coordinates; Bounds/tuples use left, top, right, bottom."""
        if isinstance(rect, QRect):
            geometry = QRect(rect)
        else:
            if isinstance(rect, Bounds):
                left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            else:
                left, top, right, bottom = rect
            geometry = QRect(
                round(left), round(top), max(1, round(right - left)),
                max(1, round(bottom - top)),
            )
        if self.geometry() != geometry:
            self.setGeometry(geometry)
        self._update_input_mask()
        self.update()

    def _update_input_mask(self) -> None:
        """Only the thin frame receives input; its center remains click-through."""
        outer = QRegion(self.rect())
        inner = self.rect().adjusted(
            self._HIT_WIDTH, self._HIT_WIDTH,
            -self._HIT_WIDTH, -self._HIT_WIDTH,
        )
        self.setMask(outer.subtracted(QRegion(inner)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_input_mask()

    def _interaction_at(self, point: QPoint) -> str:
        left = point.x() < self._HIT_WIDTH
        right = point.x() >= self.width() - self._HIT_WIDTH
        top = point.y() < self._HIT_WIDTH
        bottom = point.y() >= self.height() - self._HIT_WIDTH
        if top and abs(point.x() - self.width() // 2) <= self._MOVE_HANDLE_HALF_WIDTH:
            return "move"
        horizontal = "left" if left else "right" if right else ""
        vertical = "top" if top else "bottom" if bottom else ""
        return f"{vertical}_{horizontal}".strip("_")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_mode = self._interaction_at(event.position().toPoint())
        if not self._drag_mode:
            return
        self._drag_origin = event.globalPosition().toPoint()
        self._drag_geometry = self.geometry()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._drag_mode:
            self._update_cursor(self._interaction_at(event.position().toPoint()))
            return
        delta = event.globalPosition().toPoint() - self._drag_origin
        geometry = self._geometry_for_drag(self._drag_geometry, delta, self._drag_mode)
        self.rect_change_requested.emit(geometry)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_mode:
            self._drag_mode = ""
            event.accept()

    def _geometry_for_drag(self, start: QRect, delta: QPoint, mode: str) -> QRect:
        if mode == "move":
            return start.translated(delta)
        left, top, right, bottom = start.left(), start.top(), start.right() + 1, start.bottom() + 1
        if "left" in mode:
            left = min(left + delta.x(), right - self._MIN_SIZE)
        if "right" in mode:
            right = max(right + delta.x(), left + self._MIN_SIZE)
        if "top" in mode:
            top = min(top + delta.y(), bottom - self._MIN_SIZE)
        if "bottom" in mode:
            bottom = max(bottom + delta.y(), top + self._MIN_SIZE)
        return QRect(left, top, right - left, bottom - top)

    def _update_cursor(self, mode: str) -> None:
        cursor = {
            "move": Qt.CursorShape.SizeAllCursor,
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
            "top_left": Qt.CursorShape.SizeFDiagCursor,
            "bottom_right": Qt.CursorShape.SizeFDiagCursor,
            "top_right": Qt.CursorShape.SizeBDiagCursor,
            "bottom_left": Qt.CursorShape.SizeBDiagCursor,
        }.get(mode, Qt.CursorShape.ArrowCursor)
        self.setCursor(cursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(244, 225, 255, 9))
        painter.setPen(QPen(QColor(236, 190, 232, 112), 2.5))
        border = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(border, 14, 14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(236, 190, 232, 145))
        painter.drawRoundedRect(
            QRectF(self.width() / 2 - 22, 2, 44, 5), 2.5, 2.5
        )
