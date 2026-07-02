from __future__ import annotations

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.movement import Bounds


class FenceOverlayWindow(QWidget):
    """Click-through, non-activating visual for a fence rectangle."""

    def __init__(self) -> None:
        super().__init__(None)
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("")

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
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(244, 225, 255, 9))
        painter.setPen(QPen(QColor(236, 190, 232, 112), 2.5))
        border = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(border, 14, 14)
