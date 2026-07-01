from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt


class EdgeResizeController:
    """Reusable frameless-window edge resize logic."""

    MARGIN = 14

    def __init__(self, window) -> None:
        self.window = window
        self.edges = Qt.Edge(0)
        self.origin: QPoint | None = None
        self.geometry: QRect | None = None

    def hit_test(self, point: QPoint) -> Qt.Edge:
        edges = Qt.Edge(0)
        rect = self.window.rect()
        if point.x() <= self.MARGIN:
            edges |= Qt.Edge.LeftEdge
        elif point.x() >= rect.width() - self.MARGIN:
            edges |= Qt.Edge.RightEdge
        if point.y() <= self.MARGIN:
            edges |= Qt.Edge.TopEdge
        elif point.y() >= rect.height() - self.MARGIN:
            edges |= Qt.Edge.BottomEdge
        return edges

    def begin(self, global_pos: QPoint, local_pos: QPoint) -> bool:
        self.edges = self.hit_test(local_pos)
        if not self.edges:
            return False
        self.origin = global_pos
        self.geometry = self.window.geometry()
        return True

    def begin_native(self, global_pos: QPoint, local_pos: QPoint) -> bool:
        """Ask the OS window manager to resize; reliable for transparent windows."""
        edges = self.hit_test(local_pos)
        if not edges:
            return False
        handle = self.window.windowHandle()
        if handle is not None and handle.startSystemResize(edges):
            return True
        return self.begin(global_pos, local_pos)

    def update(self, global_pos: QPoint) -> bool:
        if not self.edges or self.origin is None or self.geometry is None:
            return False
        delta = global_pos - self.origin
        rect = QRect(self.geometry)
        if self.edges & Qt.Edge.LeftEdge:
            rect.setLeft(rect.left() + delta.x())
        if self.edges & Qt.Edge.RightEdge:
            rect.setRight(rect.right() + delta.x())
        if self.edges & Qt.Edge.TopEdge:
            rect.setTop(rect.top() + delta.y())
        if self.edges & Qt.Edge.BottomEdge:
            rect.setBottom(rect.bottom() + delta.y())
        rect.setWidth(max(self.window.minimumWidth(), rect.width()))
        rect.setHeight(max(self.window.minimumHeight(), rect.height()))
        self.window.setGeometry(rect)
        return True

    def end(self) -> None:
        self.edges = Qt.Edge(0)
        self.origin = None
        self.geometry = None
