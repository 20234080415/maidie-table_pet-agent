"""Maidie production desktop pet entry point."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from ai.client import OpenAICompatibleClient
from ai.router import AIRouter
from core.pet import PetController
from core.actions import ActionRegistry
from core.settings import ConfigStore
from core.plugins.network import NetworkPlugin
from core.tools import TimeTool, ToolRegistry, WeatherTool
from input.manager import InputManager
from memory.memory import ConversationMemory
from ui.window import PetWindow
from utils.logger import setup_logger


ROOT = Path(__file__).resolve().parent


def build_application() -> tuple[QApplication, PetWindow, PetController, InputManager]:
    logger = setup_logger(ROOT / "logs" / "maidie.log")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Maidie")
    app.setQuitOnLastWindowClosed(True)

    config_store = ConfigStore(ROOT / "config" / "config.json")
    config = config_store.load()
    chat_client, codex_client = OpenAICompatibleClient.clients_from_config(
        ROOT / "config" / "config.json"
    )
    network_plugin = NetworkPlugin(config.get("network", {}))
    tool_registry = ToolRegistry([TimeTool(), WeatherTool()])
    router = AIRouter(
        chat_client=chat_client,
        codex_client=codex_client,
        network_plugin=network_plugin,
        tool_registry=tool_registry,
    )
    chat_client.personality_prompt = config_store.personality_prompt(config)
    memory = ConversationMemory(ROOT / "memory" / "memories.db")

    movement_options = dict(config.get("movement", {}))
    cursor_chase = bool(movement_options.pop("cursor_chase", False))
    controller = PetController(
        ai_router=router,
        memory=memory,
        logger=logger,
        movement_options=movement_options,
        config_store=config_store,
        action_registry=ActionRegistry(ROOT / "assets" / "actions" / "actions.json"),
    )
    controller.cursor_chase = cursor_chase
    controller.register_plugin(network_plugin)
    window = PetWindow(
        controller=controller,
        assets_dir=ROOT / "assets",
        options=config.get("window", {}),
    )
    input_manager = InputManager(window.global_rect)
    input_manager.cursor_moved.connect(controller.on_cursor_moved)
    input_manager.cursor_near.connect(controller.on_cursor_near)
    input_manager.cursor_hover.connect(controller.on_cursor_hover)
    return app, window, controller, input_manager


def main() -> int:
    app, window, _controller, _input_manager = build_application()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
