from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QLabel


class SpeechBubble(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setMaximumWidth(260)
        self._tail_side = "bottom"
        self._stream_text = ""
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._apply_tail_margins()
        self.setStyleSheet("""
            QLabel { background: transparent; color: #4a2938;
              font-size: 14px;
              font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'SimSun'; }
        """)
        self.hide()

    def set_tail(self, side: str) -> None:
        if side not in {"top", "bottom", "left", "right"}:
            side = "bottom"
        self._tail_side = side
        self._apply_tail_margins()
        self.update()

    def _apply_tail_margins(self) -> None:
        margins = {"top": 9, "bottom": 9, "left": 12, "right": 12}
        margins[self._tail_side] += 9
        self.setContentsMargins(
            margins["left"], margins["top"], margins["right"], margins["bottom"]
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tail = 9.0
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self._tail_side == "bottom":
            rect.adjust(0, 0, 0, -tail)
        elif self._tail_side == "top":
            rect.adjust(0, tail, 0, 0)
        elif self._tail_side == "left":
            rect.adjust(tail, 0, 0, 0)
        else:
            rect.adjust(0, 0, -tail, 0)

        shadow = QPainterPath()
        shadow.addRoundedRect(rect.translated(0, 2), 15, 15)
        painter.fillPath(shadow, QColor(76, 35, 55, 28))

        path = QPainterPath()
        path.addRoundedRect(rect, 15, 15)
        cx, cy = rect.center().x(), rect.center().y()
        if self._tail_side == "bottom":
            path.moveTo(cx - 7, rect.bottom() - 1)
            path.lineTo(cx, rect.bottom() + tail)
            path.lineTo(cx + 7, rect.bottom() - 1)
        elif self._tail_side == "top":
            path.moveTo(cx - 7, rect.top() + 1)
            path.lineTo(cx, rect.top() - tail)
            path.lineTo(cx + 7, rect.top() + 1)
        elif self._tail_side == "left":
            path.moveTo(rect.left() + 1, cy - 7)
            path.lineTo(rect.left() - tail, cy)
            path.lineTo(rect.left() + 1, cy + 7)
        else:
            path.moveTo(rect.right() - 1, cy - 7)
            path.lineTo(rect.right() + tail, cy)
            path.lineTo(rect.right() - 1, cy + 7)
        path.closeSubpath()
        painter.fillPath(path, QColor(255, 248, 250, 244))
        painter.setPen(QPen(QColor(213, 137, 169, 205), 1.35))
        painter.drawPath(path)
        painter.end()
        super().paintEvent(event)

    def show_message(self, text: str, duration_ms: int = 6000) -> None:
        self._stream_text = text
        self.setText(text)
        self.adjustSize()
        self.show()
        self.raise_()
        self._hide_timer.start(duration_ms)

    def begin_stream(self) -> None:
        self._hide_timer.stop()
        self._stream_text = ""
        self.setText("…")
        self.adjustSize()
        self.show()
        self.raise_()

    def append_stream(self, delta: str) -> None:
        self._stream_text += delta
        self.setText(self._stream_text or "…")
        self.adjustSize()

    def scale_for_window(self, width: int) -> None:
        scale = max(0.8, min(1.45, width / 320))
        font = self.font()
        font.setPixelSize(max(12, int(14 * scale)))
        self.setFont(font)
