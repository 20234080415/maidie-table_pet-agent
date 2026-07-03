from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QVBoxLayout

from ui.dialogs import BASE_STYLE
from ui.settings.help_page import HelpPage


class HelpDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("帮助与说明")
        self.resize(640, 560)
        self.setStyleSheet(BASE_STYLE)
        layout = QVBoxLayout(self)
        layout.addWidget(HelpPage(self))
