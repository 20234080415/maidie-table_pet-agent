from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFocusEvent, QKeyEvent
from PyQt6.QtWidgets import QLineEdit


class ChatInput(QLineEdit):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setPlaceholderText("和 Maidie 说点什么…")
        self.setStyleSheet("""
            QLineEdit { background: rgba(255, 250, 252, 242); color: #44283a;
              border: 2px solid #df8fb1; border-radius: 12px; padding: 7px 10px; }
        """)
        self.returnPressed.connect(self._submit)
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.setInterval(10_000)
        self._dismiss_timer.timeout.connect(self.dismiss)
        self.textEdited.connect(lambda _text: self._dismiss_timer.start())
        self.hide()

    def open(self) -> None:
        self.show()
        self.raise_()
        self.setFocus()
        self._dismiss_timer.start()

    def dismiss(self) -> None:
        self._dismiss_timer.stop()
        self.clearFocus()
        self.hide()

    def _submit(self) -> None:
        text = self.text().strip()
        if text:
            self.submitted.emit(text)
            self.clear()
        self.dismiss()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        # Defer until Qt finishes transferring focus, then close the editor.
        QTimer.singleShot(0, self.dismiss)
