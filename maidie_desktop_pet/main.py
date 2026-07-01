"""Maidie production desktop pet entry point."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from ai.client import OpenAICompatibleClient
from ai.router import AIRouter
from core.pet import PetController
from core.actions import ActionRegistry
from core.settings import ConfigStore
from input.manager import InputManager
from memory.memory import ConversationMemory
from ui.window import PetWindow
from ui.tray import MaidieTrayIcon
from utils.logger import setup_logger
from utils.paths import resource_path, user_data_path


def build_application() -> tuple[QApplication, PetWindow, PetController, InputManager]:
    logger = setup_logger(user_data_path("logs", "maidie.log"))
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Maidie")

    config_path = user_data_path("config", "config.json")
    config_store = ConfigStore(config_path, resource_path("config", "default.json"))
    config = config_store.load()
    chat_client, codex_client = OpenAICompatibleClient.clients_from_config(config_path)
    router = AIRouter(chat_client=chat_client, codex_client=codex_client)
    chat_client.personality_prompt = config_store.personality_prompt(config)
    memory = ConversationMemory(user_data_path("memory", "conversations.json"))

    movement_options = dict(config.get("movement", {}))
    cursor_chase = bool(movement_options.pop("cursor_chase", False))
    controller = PetController(
        ai_router=router,
        memory=memory,
        logger=logger,
        movement_options=movement_options,
        config_store=config_store,
        action_registry=ActionRegistry(resource_path("assets", "actions", "actions.json")),
    )
    controller.cursor_chase = cursor_chase
    window = PetWindow(
        controller=controller,
        assets_dir=resource_path("assets"),
        options=config.get("window", {}),
    )
    input_manager = InputManager(window.global_rect)
    input_manager.cursor_moved.connect(controller.on_cursor_moved)
    input_manager.cursor_near.connect(controller.on_cursor_near)
    input_manager.cursor_hover.connect(controller.on_cursor_hover)
    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    app.setQuitOnLastWindowClosed(not tray_available)
    window.set_tray_available(tray_available)
    if tray_available:
        window.tray_icon = MaidieTrayIcon(window, resource_path("assets", "maidie.png"))
        window.tray_icon.show()
    return app, window, controller, input_manager


def main() -> int:
    app, window, _controller, _input_manager = build_application()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
