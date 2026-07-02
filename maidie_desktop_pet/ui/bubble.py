from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QTextCursor
from PyQt6.QtWidgets import QTextBrowser


class SpeechBubble(QTextBrowser):
    layout_changed = pyqtSignal()

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
        self.setReadOnly(True)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setMinimumWidth(120)
        self.setMaximumWidth(260)
        self.setMaximumHeight(240)
        self._tail_side = "bottom"
        self._stream_text = ""
        self._placeholder = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._apply_tail_margins()
        self.setStyleSheet("""
            QTextBrowser { background: transparent; color: #4a2938; border: none;
              font-size: 14px;
              font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'SimSun'; }
        """)
        self.viewport().setStyleSheet("background: transparent;")
        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(120)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._size_animation = QPropertyAnimation(self, b"size", self)
        self._size_animation.setDuration(180)
        self._size_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.resize(self.minimumWidth(), 48)
        self.hide()

    def set_tail(self, side: str) -> None:
        if side not in {"top", "bottom", "left", "right"}:
            side = "bottom"
        if side == self._tail_side:
            return
        self._tail_side = side
        self._apply_tail_margins()
        self._fit_content(animate=self.isVisible())
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
        self.clear()
        self._stream_text = ""
        self._placeholder = False
        self.append_text(text)
        self.show()
        self.raise_()
        self._hide_timer.start(duration_ms)

    def begin_stream(self) -> None:
        self._hide_timer.stop()
        self._size_animation.stop()
        self.clear()
        self._stream_text = ""
        self._placeholder = True
        self.resize(self.minimumWidth(), 48)
        self.show()
        self.raise_()
        self._insert_text("…")

    def append_stream(self, delta: str) -> None:
        self.append_text(delta)

    def append_text(self, fragment: str) -> None:
        if not fragment:
            return
        if self._placeholder:
            self.clear()
            self._placeholder = False
        self._stream_text += fragment
        self._insert_text(fragment)

    def finish_stream(self, duration_ms: int = 6000) -> None:
        self._hide_timer.start(duration_ms)

    def _insert_text(self, fragment: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(fragment)
        self.setTextCursor(cursor)
        self._fit_content(animate=True)
        bar = self.verticalScrollBar()
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(bar.value())
        self._scroll_animation.setEndValue(bar.maximum())
        self._scroll_animation.start()

    def adjustSize(self) -> None:
        # Overlay positioning runs on every animation frame. Do not snap to the
        # destination while an expansion is in progress.
        if self._size_animation.state() != QPropertyAnimation.State.Running:
            self._fit_content(animate=False)

    def _fit_content(self, *, animate: bool) -> None:
        horizontal = self.contentsMargins().left() + self.contentsMargins().right() + 8
        vertical = self.contentsMargins().top() + self.contentsMargins().bottom() + 8
        lines = (self.toPlainText() or "…").splitlines() or ["…"]
        natural_width = max(self.fontMetrics().horizontalAdvance(line) for line in lines)
        width = max(
            self.minimumWidth(),
            min(self.maximumWidth(), natural_width + horizontal + 14),
        )
        self.document().setTextWidth(max(40, width - horizontal))
        height = round(self.document().size().height()) + vertical
        target = QSize(width, min(self.maximumHeight(), max(48, height)))
        if animate and self.isVisible() and target != self.size():
            self._size_animation.stop()
            self._size_animation.setStartValue(self.size())
            self._size_animation.setEndValue(target)
            self._size_animation.start()
        elif self._size_animation.state() != QPropertyAnimation.State.Running:
            self.resize(target)
        # Keep the desktop bubble visually clean; the hidden scrollbar still
        # provides the animated viewport offset used above.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.layout_changed.emit()

    def scale_for_window(self, width: int) -> None:
        scale = max(0.8, min(1.45, width / 320))
        font = self.font()
        font.setPixelSize(max(12, int(14 * scale)))
        self.setFont(font)
