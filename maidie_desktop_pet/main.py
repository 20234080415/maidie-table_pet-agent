"""Maidie production desktop pet entry point."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from ai.client import OpenAICompatibleClient
from core.brain import BrainRouter, Synthesizer
from core.pet import PetController
from core.actions import ActionRegistry
from core.settings import ConfigStore
from core.plugins.network import NetworkPlugin
from core.tools import (MemoryTool, ScreenTool, SearchTool, SystemTool, TimeTool,
                        ToolRegistry, WeatherTool)
from core.agent import ConfirmationBroker
from core.awareness import AppTracker, ClipboardTracker, IdleDetector, MouseTracker, WindowTracker
from core.awareness.context import AwarenessContext
from core.proactive import ProactiveEngine, ProactiveRuntime
from core.tasks import TaskScheduler
from core.vision import ScreenReader
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
    memory = ConversationMemory(ROOT / "memory" / "memories.db")
    confirmation_broker = ConfirmationBroker()
    system_tool = SystemTool(confirmation_callback=confirmation_broker.request)
    proactive_options = config.get("proactive", {})
    vision_options = config.get("vision", {})
    idle_detector = IdleDetector(float(proactive_options.get("idle_trigger_seconds", 300)))
    screen_reader = ScreenReader(
        enabled=bool(vision_options.get("enabled", False)),
        interval_seconds=float(vision_options.get("interval_seconds", 60)),
    )
    awareness = AwarenessContext(
        MouseTracker(idle_detector), WindowTracker(), AppTracker(), screen_reader, ClipboardTracker()
    )
    tool_registry = ToolRegistry([
        TimeTool(), WeatherTool(), SearchTool(network_plugin), ScreenTool(awareness),
        MemoryTool(memory), system_tool,
    ])
    personality_prompt = config_store.personality_prompt(config)
    router = BrainRouter(
        chat_client=chat_client,
        codex_client=codex_client,
        tool_registry=tool_registry,
        memory=memory,
        synthesizer=Synthesizer(chat_client, codex_client,
                                personality_prompt=personality_prompt),
    )
    chat_client.personality_prompt = personality_prompt
    proactive_engine = ProactiveEngine(
        enabled=bool(proactive_options.get("enabled", False)),
        cooldown_seconds=float(proactive_options.get("cooldown_seconds", 900)),
        idle_trigger_seconds=float(proactive_options.get("idle_trigger_seconds", 300)),
        coding_trigger_seconds=float(proactive_options.get("coding_trigger_seconds", 7200)),
        random_chance=float(proactive_options.get("random_chance", 0.05)),
    )
    scheduler = TaskScheduler(ROOT / "memory" / "scheduled_tasks.json")
    proactive_runtime = ProactiveRuntime(awareness, proactive_engine, scheduler, tool_registry, memory)

    movement_options = dict(config.get("movement", {}))
    cursor_chase = bool(movement_options.pop("cursor_chase", False))
    controller = PetController(
        ai_router=router,
        memory=memory,
        logger=logger,
        movement_options=movement_options,
        config_store=config_store,
        action_registry=ActionRegistry(ROOT / "assets" / "actions" / "actions.json"),
        proactive_runtime=proactive_runtime,
        proactive_tick_seconds=int(proactive_options.get("tick_seconds", 45)),
    )
    controller.cursor_chase = cursor_chase
    controller.register_plugin(network_plugin)
    window = PetWindow(
        controller=controller,
        assets_dir=ROOT / "assets",
        options=config.get("window", {}),
        confirmation_broker=confirmation_broker,
        fence_options=config.get("fence", {}),
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
