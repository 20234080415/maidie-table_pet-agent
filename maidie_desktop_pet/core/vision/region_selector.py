from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget


class RegionSelector(QWidget):
    """Non-blocking top-level overlay for selecting a global screen rectangle."""

    region_selected = pyqtSignal(QRect)
    selection_cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(None)
        self._start: QPoint | None = None
        self._current: QPoint | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def begin(self) -> None:
        screens = QApplication.screens()
        if not screens:
            self.selection_cancelled.emit()
            return
        bounds = screens[0].geometry()
        for screen in screens[1:]:
            bounds = bounds.united(screen.geometry())
        self.setGeometry(bounds)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._current = self._start
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._start is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        self._current = event.position().toPoint()
        local_rect = QRect(self._start, self._current).normalized()
        self._complete_selection(local_rect)

    def _complete_selection(self, local_rect: QRect) -> None:
        self.hide()
        self._start = self._current = None
        if local_rect.width() < 20 or local_rect.height() < 20:
            self.selection_cancelled.emit()
            return
        global_rect = QRect(self.geometry().topLeft() + local_rect.topLeft(), local_rect.size())
        self.region_selected.emit(global_rect)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self._start = self._current = None
            self.selection_cancelled.emit()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 12, 18, 150))
        painter.setPen(QColor(255, 255, 255, 235))
        painter.drawText(
            self.rect().adjusted(0, 24, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "拖拽选择要让 Maidie 看的区域，按 Esc 取消",
        )
        if self._start is None or self._current is None:
            return
        selection = QRect(self._start, self._current).normalized()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(selection, Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QPen(QColor(244, 151, 180), 3))
        painter.drawRect(selection)
