from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


class MaidieTrayIcon(QSystemTrayIcon):
    """Small system-tray adapter for window visibility and explicit shutdown."""

    def __init__(self, window, icon_path: Path):
        super().__init__(QIcon(str(icon_path)), window)
        self.window = window
        self.menu = QMenu()
        show_action = QAction("显示 Maidie", self.menu)
        hide_action = QAction("隐藏 Maidie", self.menu)
        settings_action = QAction("设置", self.menu)
        quit_action = QAction("退出", self.menu)
        show_action.triggered.connect(window.show_from_tray)
        hide_action.triggered.connect(window.hide_to_tray)
        settings_action.triggered.connect(window.show_settings)
        quit_action.triggered.connect(window.request_quit)
        self.menu.addActions((show_action, hide_action, settings_action))
        self.menu.addSeparator()
        self.menu.addAction(quit_action)
        self.setContextMenu(self.menu)
        self.setToolTip("Maidie Desktop Pet")
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.window.show_from_tray()
