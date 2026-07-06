"""Maidie production desktop pet entry point."""
from __future__ import annotations

import json
import signal
import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, Qt, QTimer
from PyQt6.QtWidgets import QApplication


_webengine_ready = False


def _prepare_webengine() -> None:
    global _webengine_ready
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    try:
        import PyQt6.QtWebEngineWidgets  # noqa: F401
        _webengine_ready = True
    except ImportError:
        _webengine_ready = False


def webengine_ready() -> bool:
    return _webengine_ready


def force_sprite_requested(argv: list[str] | None = None) -> bool:
    return "--force-sprite" in (sys.argv[1:] if argv is None else argv)


def apply_safe_backend_override(config: dict, force_sprite: bool) -> dict:
    if not force_sprite:
        return config
    overridden = dict(config)
    overridden["animation"] = dict(config.get("animation", {}), backend="sprite")
    return overridden

from ai.client import OpenAICompatibleClient
from core.brain import BrainRouter, Synthesizer
from core.pet import PetController
from core.actions import ActionRegistry
from core.settings import ConfigStore
from core.plugins.network import NetworkPlugin
from core.tools import (CodingAgentTool, MemoryTool, ScreenTool, SearchTool, SystemTool, TimeTool,
                        ToolRegistry, WeatherTool)
from core.agent import ConfirmationBroker
from core.awareness import AppTracker, ClipboardTracker, IdleDetector, MouseTracker, WindowTracker
from core.awareness.context import AwarenessContext
from core.proactive import ProactiveEngine, ProactiveRuntime
from core.tasks import TaskScheduler
from core.vision import ScreenReader, VisionService
from core.version import APP_NAME, APP_VERSION
from animation.live2d_web import resolve_animation_backend
from animation.model_manager import AnimationModelRegistry
from input.manager import InputManager
from memory.memory import ConversationMemory
from ui.window import PetWindow
from utils.logger import setup_logger


ROOT = Path(__file__).resolve().parent


def _create_main_window(config: dict, controller: PetController,
                        confirmation_broker, logger):
    animation = dict(config.get("animation", {}))
    requested = str(animation.get("backend", "sprite"))
    resolved, status = resolve_animation_backend(animation)
    if requested == "live2d_web" and resolved == "live2d_web":
        registry = AnimationModelRegistry(
            animation.get("live2d_models", []), animation.get("current_model_id", "")
        )
        model = registry.resolve_current_model()
        try:
            from ui.live2d_main_window import create_live2d_main_window
            window, result = create_live2d_main_window(
                model, controller, ROOT / "assets", config.get("window", {}),
                confirmation_broker, config.get("fence", {}), animation,
            )
        except Exception as exc:
            window, result = None, {
                "code": "live2d_main_import_failed", "message": str(exc),
            }
        if window is not None:
            logger.info("Animation backend selected: live2d_web (%s)", status.message)
            return window, "live2d_web", status
        logger.warning(
            "Live2D main backend failed (%s): %s; falling back to Sprite.",
            result.get("code", "unknown"), result.get("message", "unknown error"),
        )
    elif requested == "live2d_web":
        logger.warning(
            "Live2D backend unavailable (%s): %s; falling back to Sprite.",
            status.code, status.message,
        )
    window = PetWindow(
        controller=controller, assets_dir=ROOT / "assets",
        options=config.get("window", {}), confirmation_broker=confirmation_broker,
        fence_options=config.get("fence", {}),
    )
    logger.info("Animation backend selected: sprite")
    return window, "sprite", status


def build_application() -> tuple[QApplication, object, PetController, InputManager]:
    logger = setup_logger(ROOT / "logs" / "maidie.log")
    force_sprite = force_sprite_requested()
    if not force_sprite:
        _prepare_webengine()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(True)

    config_store = ConfigStore(ROOT / "config" / "config.json")
    config = config_store.load()
    if force_sprite:
        config = apply_safe_backend_override(config, True)
        logger.warning("Safe startup requested with --force-sprite; Live2D config ignored.")
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
    vision_service = VisionService()
    vision_service.reconfigure(vision_options)
    tool_registry = ToolRegistry([
        TimeTool(), WeatherTool(), SearchTool(network_plugin),
        ScreenTool(awareness, vision_service),
        MemoryTool(memory), system_tool,
        CodingAgentTool(config.get("workspace", {}), config.get("coding_agent", {})),
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
    window, _runtime_backend, _animation_status = _create_main_window(
        config, controller, confirmation_broker, logger
    )
    input_manager = InputManager(window.global_rect)
    input_manager.cursor_moved.connect(controller.on_cursor_moved)
    input_manager.cursor_near.connect(controller.on_cursor_near)
    input_manager.cursor_hover.connect(controller.on_cursor_hover)
    window.set_input_manager(input_manager)
    return app, window, controller, input_manager


def main() -> int:
    app, window, controller, _input_manager = build_application()
    logger = controller.logger
    app.aboutToQuit.connect(window.shutdown)
    interrupt_timer = QTimer()
    interrupt_timer.setInterval(200)
    interrupt_timer.timeout.connect(lambda: None)
    interrupt_timer.start()

    interrupted = False

    def handle_sigint(_signum, _frame) -> None:
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        logger.info("Maidie interrupted by user. Shutting down...")
        QTimer.singleShot(0, window.request_exit)

    previous_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, handle_sigint)
    window.show()
    try:
        exit_code = app.exec()
    except KeyboardInterrupt:
        logger.info("Maidie interrupted by user. Shutting down...")
        window.shutdown()
        exit_code = 0
    except Exception:
        logger.exception("Unhandled exception in Maidie")
        window.shutdown()
        exit_code = 1
    finally:
        interrupt_timer.stop()
        window.shutdown()
        signal.signal(signal.SIGINT, previous_sigint)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
