from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QVBoxLayout

from ui.dialogs import BASE_STYLE
from ui.settings.about_page import AboutPage


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于 Maidie")
        self.resize(520, 470)
        self.setStyleSheet(BASE_STYLE)
        layout = QVBoxLayout(self)
        layout.addWidget(AboutPage(self))
