from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QCursor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class SubtleResizeHandle(QWidget):
    """Small bottom-right affordance backed by the native window resizer."""

    def __init__(self, target: QWidget):
        super().__init__(target)
        self.target = target
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("拖动缩放 Maidie")
        self._hovered = False
        self._fallback_origin: QPoint | None = None
        self._fallback_size = None
        self.hide()

    @property
    def is_resizing(self) -> bool:
        return self._fallback_origin is not None

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height())
        edge = size - 2
        painter.setPen(QPen(QColor(73, 41, 54, 65), 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(max(2, size // 2), edge, edge, max(2, size // 2))
        painter.drawLine(max(2, size * 2 // 3), edge, edge, max(2, size * 2 // 3))
        alpha = 235 if self._hovered else 178
        painter.setPen(QPen(QColor(255, 248, 225, alpha), 1.45, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(max(2, size // 2), edge, edge, max(2, size // 2))
        painter.drawLine(max(2, size * 2 // 3), edge, edge, max(2, size * 2 // 3))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        # This handle deliberately uses custom resizing so its aspect ratio is
        # locked on every platform; edge dragging remains available separately.
        self._fallback_origin = event.globalPosition().toPoint()
        self._fallback_size = self.target.size()
        self.grabMouse()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._fallback_origin is None or self._fallback_size is None:
            return
        delta = event.globalPosition().toPoint() - self._fallback_origin
        width = self._fallback_size.width()
        height = self._fallback_size.height()
        factor = 1.0 + ((delta.x() / width) + (delta.y() / height)) / 2.0
        min_factor = max(
            self.target.minimumWidth() / width,
            self.target.minimumHeight() / height,
        )
        max_factor = min(900 / width, 1069 / height)
        factor = max(min_factor, min(max_factor, factor))
        self.target.resize(round(width * factor), round(height * factor))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._fallback_origin = None
        self._fallback_size = None
        self.releaseMouse()
        if not self.target.frameGeometry().contains(QCursor.pos()):
            self.hide()
        event.accept()
