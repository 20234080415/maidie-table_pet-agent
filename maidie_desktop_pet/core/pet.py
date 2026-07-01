from __future__ import annotations

import logging
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from typing import Any, Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.behavior import AutonomousBehaviorController, BehaviorKind
from core.movement import Bounds, MovementController, Vec2
from core.state import BehaviorPriority, PetState, StateMachine


class PetController(QObject):
    """Single source of truth for state, priorities, motion and AI orchestration."""

    state_changed = pyqtSignal(str)
    animation_changed = pyqtSignal(str)
    position_requested = pyqtSignal(float, float)
    message_received = pyqtSignal(object)
    stream_started = pyqtSignal(object)
    message_delta = pyqtSignal(str)
    request_failed = pyqtSignal(str)
    settings_changed = pyqtSignal(object)
    gaze_changed = pyqtSignal(float, float)
    _result_ready = pyqtSignal(object)
    _stream_delta_ready = pyqtSignal(str)

    def __init__(
        self,
        ai_router: Any,
        memory: Any,
        logger: logging.Logger | None = None,
        movement_options: dict[str, Any] | None = None,
        config_store: Any | None = None,
        action_registry: Any | None = None,
        proactive_runtime: Any | None = None,
        proactive_tick_seconds: int = 45,
    ) -> None:
        super().__init__()
        self.ai_router = ai_router
        self.memory = memory
        self.logger = logger or logging.getLogger(__name__)
        self.config_store = config_store
        self.action_registry = action_registry
        self.proactive_runtime = proactive_runtime
        self.state_machine = StateMachine()
        self.movement = MovementController(**(movement_options or {}))
        self.behavior = AutonomousBehaviorController()
        self.bounds = Bounds(0, 0, 1920, 1080)
        self.cursor = Vec2()
        self.cursor_chase = False
        self._busy = False
        self._pending_message = ""
        self._pending_source = "chat"
        self._pending_reaction: str | None = None
        self._listeners: dict[str, list[Callable[..., None]]] = defaultdict(list)
        self._plugins: list[Any] = []
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="maidie-ai")
        self._result_ready.connect(self._handle_result)
        self._stream_delta_ready.connect(self._handle_stream_delta)
        self._last_tick = monotonic()
        self._state_token = 0
        self._proactive_timer = QTimer(self)
        self._proactive_timer.timeout.connect(self._proactive_tick)
        self._proactive_timer.start(max(30, min(60, int(proactive_tick_seconds))) * 1000)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(16)

    @property
    def state(self) -> PetState:
        return self.state_machine.state

    def on(self, event: str, callback: Callable[..., None]) -> None:
        self._listeners[event].append(callback)

    def register_plugin(self, plugin: Any) -> None:
        self._plugins.append(plugin)

    def clear_memory(self) -> None:
        self.memory.clear()
        self._broadcast("on_memory_cleared")

    def recent_chats(self) -> list[dict[str, str]]:
        return self.memory.get_recent()

    def settings_snapshot(self) -> dict[str, Any]:
        return self.config_store.public_settings() if self.config_store else {}

    def apply_settings(self, values: dict[str, Any]) -> None:
        if not self.config_store:
            return
        config = self.config_store.update_user_settings(values)
        ai = config.get("ai", {})
        technical = config.get("codex", {})
        environment_key = (
            os.getenv("DEEPSEEK_API_KEY") if ai.get("provider", "deepseek") == "deepseek" else ""
        )
        key = environment_key or ai.get("api_key", "")
        personality = self.config_store.personality_prompt(config)
        chat_client = self.ai_router.chat_client
        technical_client = self.ai_router.codex_client
        if hasattr(chat_client, "reconfigure"):
            chat_client.reconfigure(
                key,
                ai.get("base_url", "https://api.deepseek.com"),
                ai.get("model", "deepseek-v4-flash"),
                personality,
            )
        if hasattr(technical_client, "reconfigure"):
            technical_client.reconfigure(
                key,
                technical.get("base_url") or ai.get("base_url", "https://api.deepseek.com"),
                technical.get("model", "deepseek-v4-pro"),
            )
        synthesizer = getattr(self.ai_router, "synthesizer", None)
        if synthesizer is not None:
            synthesizer.personality_prompt = personality
        for plugin in self._plugins:
            if hasattr(plugin, "configure"):
                plugin.configure(config.get("network", {}))
        if self.proactive_runtime:
            proactive = config.get("proactive", {})
            engine = self.proactive_runtime.engine
            engine.enabled = bool(proactive.get("enabled", False))
            engine.cooldown_seconds = max(30.0, float(proactive.get("cooldown_seconds", 900)))
            tick_seconds = max(30, min(60, int(proactive.get("tick_seconds", 45))))
            self._proactive_timer.setInterval(tick_seconds * 1000)
            screen_reader = self.proactive_runtime.awareness.screen_reader
            if screen_reader:
                vision = config.get("vision", {})
                screen_reader.enabled = bool(vision.get("enabled", False))
                screen_reader.interval_seconds = max(30.0, float(vision.get("interval_seconds", 60)))
        public = self.config_store.public_settings()
        self.settings_changed.emit(public)
        self._broadcast("on_settings_changed", public)

    def _broadcast(self, event: str, payload: Any = None) -> None:
        for callback in tuple(self._listeners[event]):
            callback(payload)
        for plugin in tuple(self._plugins):
            try:
                plugin.on_event(event, payload)
            except Exception:
                self.logger.exception("Plugin failed while handling %s", event)

    def set_state(
        self,
        state: PetState,
        priority: BehaviorPriority,
        lock_ms: int = 0,
        force: bool = False,
        animation: str | None = None,
    ) -> bool:
        """The only state transition interface in the application."""
        if not self.state_machine.transition(state, priority, lock_ms, force):
            return False
        self._state_token += 1
        self.state_changed.emit(state.value)
        self.animation_changed.emit(animation or self._animation_for_state(state))
        self._broadcast("on_state_change", {
            "state": state.value,
            "priority": int(priority),
        })
        return True

    def _animation_for_state(self, state: PetState) -> str:
        if state in (PetState.WALK, PetState.RUN):
            return f"{state.value}-{self.movement.direction}"
        return {
            PetState.REACTING: "reacting",
            PetState.SLEEPING: "sleeping",
        }.get(state, state.value)

    def set_screen_bounds(self, left: float, top: float, right: float, bottom: float) -> None:
        self.bounds = Bounds(left, top, right, bottom)

    def sync_geometry(self, x: float, y: float, width: float, height: float) -> None:
        self.movement.sync_geometry(x, y, width, height)

    def on_pet_dragged(
        self, x: float, y: float, width: float, height: float, drag_dx: float = 0.0
    ) -> None:
        self.movement.stop()
        self.sync_geometry(x, y, width, height)
        self.behavior.postpone(2.5)
        if drag_dx > 30:
            self._play_action("dizzy-right", force=True)
        else:
            self.set_state(PetState.IDLE, BehaviorPriority.USER_CLICK, 250, force=True)

    def on_pet_clicked(self) -> None:
        self.movement.stop()
        self._broadcast("on_click")
        self.set_state(PetState.REACTING, BehaviorPriority.USER_CLICK, 520, animation="reacting")
        if self._busy:
            QTimer.singleShot(540, self._restore_after_interaction)
        else:
            QTimer.singleShot(540, lambda: self.submit_text("主人点了点你，请自然地回应。"))

    def on_headpat(self) -> None:
        """Play a local head-pat reaction without spending an API request."""
        self.movement.stop()
        self._broadcast("on_headpat")
        self._play_action("headpat")

    def on_facepoke(self) -> None:
        self.movement.stop()
        self._broadcast("on_facepoke")
        self._play_action("facepoke")

    def _play_action(self, name: str, force: bool = False) -> bool:
        definition = self.action_registry.get(name) if self.action_registry else None
        if not definition or not self.action_registry.can_trigger(name):
            return False
        try:
            state = PetState(definition.state)
            priority = BehaviorPriority(definition.priority)
        except ValueError:
            self.logger.warning("Invalid action state or priority: %s", name)
            return False
        changed = self.set_state(
            state,
            priority,
            max(0, definition.duration_ms - 50),
            force=force,
            animation=name,
        )
        if not changed:
            return False
        self.action_registry.mark_triggered(name)
        if self._busy and priority >= BehaviorPriority.CURSOR_INTERACTION:
            QTimer.singleShot(definition.duration_ms, self._restore_after_interaction)
        else:
            token = self._state_token
            QTimer.singleShot(
                definition.duration_ms, lambda: self._recover_if_current(token)
            )
        return True

    def on_chat_opened(self) -> None:
        if not self._busy:
            self.movement.stop()
            self.set_state(
                PetState.THINKING,
                BehaviorPriority.USER_CLICK,
                1200,
                animation="waiting",
            )

    def submit_text(self, message: str, proactive: bool = False) -> None:
        message = message.strip()
        if not message or self._busy:
            return
        self._busy = True
        self._pending_message = message
        self._pending_source = self.ai_router.classify(message)
        self._pending_reaction = (
            self.action_registry.match_message(message) if self.action_registry else None
        )
        self.stream_started.emit({"source": self._pending_source})
        self.movement.stop()
        target_state = PetState.REMINDING if proactive else PetState.THINKING
        target_priority = BehaviorPriority.PROACTIVE if proactive else BehaviorPriority.AI_TALKING
        self.set_state(target_state, target_priority, 400, force=True,
                       animation="happy" if proactive else None)
        context = self.memory.get_recent()
        memory_context = self.memory.prompt_context() if hasattr(self.memory, "prompt_context") else ""
        if memory_context:
            context.append({"memory": memory_context})
        future = self._executor.submit(self._run_stream_request, message, context)
        future.add_done_callback(self._finish_request)

    def _run_stream_request(self, message: str, context: list[dict[str, Any]]) -> dict[str, str]:
        return self.ai_router.ask_stream(
            message,
            context,
            lambda delta: self._stream_delta_ready.emit(delta),
        )

    def _handle_stream_delta(self, delta: str) -> None:
        self.message_delta.emit(delta)

    def _finish_request(self, future: Any) -> None:
        try:
            self._result_ready.emit(future.result())
        except Exception as exc:
            self.logger.exception("AI request failed")
            self._result_ready.emit({"error": str(exc)})

    def _handle_result(self, result: dict[str, Any]) -> None:
        self._busy = False
        if "error" in result:
            error_message = str(result["error"])
            result = {
                "text": "唔，脑内频道暂时断线了，请稍后再试。",
                "emotion": "sad",
                "action": "talk",
                "state": "talking",
                "source": self._pending_source,
            }
            self.request_failed.emit(error_message)

        response = {
            "text": str(result.get("text", "Maidie 在这里哦。")),
            "emotion": str(result.get("emotion", "idle")),
            "action": str(result.get("action", "talk")),
            "state": str(result.get("state", "talking")),
            "source": str(result.get("source", "chat")),
        }
        if self._pending_reaction:
            animation = self._pending_reaction
        elif response["source"] == "codex":
            animation = "review"
        elif response["emotion"] in ("happy", "excited"):
            animation = "happy"
        elif response["emotion"] == "sad":
            animation = "failed"
        else:
            animation = "talking"
        duration = min(9000, max(2800, len(response["text"]) * 90))
        self._activate_talking(animation, duration)
        self.message_received.emit(response)
        self.memory.save(self._pending_message, response["text"])
        if (
            hasattr(self.memory, "save_extracted")
            and hasattr(self.ai_router, "extract_memories")
            and (
                not hasattr(self.memory, "can_extract")
                or self.memory.can_extract(self._pending_message, response["text"])
            )
        ):
            self._executor.submit(
                self._extract_and_store_memories,
                self._pending_message,
                response["text"],
            )
        self._broadcast("on_message", response)
        self._pending_reaction = None

    def _extract_and_store_memories(self, message: str, response: str) -> None:
        try:
            extracted = self.ai_router.extract_memories(message, response)
            self.memory.save_extracted(extracted)
        except Exception:
            self.logger.exception("Memory extraction failed")

    def _activate_talking(self, animation: str, duration: int) -> None:
        if self.action_registry and self.action_registry.get(animation):
            if not self.action_registry.can_trigger(animation):
                animation = "talking"
        changed = self.set_state(
            PetState.TALKING,
            BehaviorPriority.AI_TALKING,
            800,
            animation=animation,
        )
        if not changed:
            QTimer.singleShot(560, lambda: self._activate_talking(animation, duration))
            return
        if self.action_registry and self.action_registry.get(animation):
            self.action_registry.mark_triggered(animation)
        token = self._state_token
        QTimer.singleShot(duration, lambda: self._recover_if_current(token))

    def _restore_after_interaction(self) -> None:
        if self._busy:
            self.set_state(PetState.THINKING, BehaviorPriority.AI_TALKING, 300)
        else:
            self._recover_if_current(self._state_token)

    def _recover_if_current(self, token: int) -> None:
        if token != self._state_token:
            return
        motion_state = self.movement.classify_state()
        priority = BehaviorPriority.AUTONOMOUS if motion_state != PetState.IDLE else BehaviorPriority.IDLE
        self.set_state(motion_state, priority, force=True)

    def on_cursor_moved(self, x: int, y: int) -> None:
        if self.proactive_runtime:
            self.proactive_runtime.awareness.mouse_tracker.record(x, y)
        self.cursor = Vec2(float(x), float(y))
        center = Vec2(
            self.movement.position.x + self.movement.window_width / 2,
            self.movement.position.y + self.movement.window_height / 2,
        )
        dx = max(-1.0, min(1.0, (self.cursor.x - center.x) / 220.0))
        dy = max(-1.0, min(1.0, (self.cursor.y - center.y) / 220.0))
        self.gaze_changed.emit(dx, dy)

    def on_cursor_near(self, near: bool) -> None:
        self._broadcast("on_cursor_near", near)
        if near and self.cursor_chase and not self._busy:
            target = Vec2(
                self.cursor.x - self.movement.window_width / 2,
                self.cursor.y - self.movement.window_height * 0.7,
            )
            self.movement.move_to(target, run=False)

    def on_cursor_hover(self, hover: bool) -> None:
        self._broadcast("on_cursor_hover", hover)
        if hover:
            self.movement.stop()
            changed = self.set_state(
                PetState.REACTING,
                BehaviorPriority.CURSOR_INTERACTION,
                850,
                animation="reacting",
            )
            if changed:
                if self._busy:
                    QTimer.singleShot(900, self._restore_after_interaction)
                else:
                    token = self._state_token
                    QTimer.singleShot(900, lambda: self._recover_if_current(token))

    def _tick(self) -> None:
        now = monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        if not self._busy and self.state_machine.can_interrupt(BehaviorPriority.AUTONOMOUS):
            intent = self.behavior.decide(
                self.bounds,
                (self.movement.window_width, self.movement.window_height),
                self.cursor,
            )
            if intent:
                if intent.kind == BehaviorKind.IDLE_PAUSE:
                    self.movement.stop()
                    changed = self.set_state(
                        PetState.THINKING,
                        BehaviorPriority.AUTONOMOUS,
                        1800,
                        animation="waiting",
                    )
                    if changed:
                        token = self._state_token
                        QTimer.singleShot(1850, lambda: self._recover_if_current(token))
                elif intent.kind == BehaviorKind.SLEEPY:
                    self.movement.stop()
                    self._play_action("sleepy")
                elif intent.target:
                    self.movement.move_to(intent.target, intent.run)

        old_position = Vec2(self.movement.position.x, self.movement.position.y)
        position = self.movement.tick(dt, self.bounds)
        if position.distance_to(old_position) > 0.01:
            self.position_requested.emit(position.x, position.y)

        motion_state = self.movement.classify_state()
        if self.state_machine.can_interrupt(BehaviorPriority.AUTONOMOUS):
            priority = BehaviorPriority.AUTONOMOUS if motion_state != PetState.IDLE else BehaviorPriority.IDLE
            self.set_state(motion_state, priority)

    def _proactive_tick(self) -> None:
        if not self.proactive_runtime or self._busy:
            return
        try:
            context, decision = self.proactive_runtime.tick()
            if decision:
                self.submit_text(decision.prompt, proactive=True)
                self._pending_reaction = decision.action
            elif self.proactive_runtime.engine.enabled and context.get("mouse_state") != "idle":
                changed = self.set_state(PetState.WATCHING, BehaviorPriority.AUTONOMOUS,
                                         900, animation="idle")
                if changed:
                    token = self._state_token
                    QTimer.singleShot(950, lambda: self._recover_if_current(token))
            elif float(context.get("idle_time", 0)) >= 300:
                self._play_action("sleepy")
        except Exception:
            self.logger.exception("Proactive Agent tick failed")

    def shutdown(self) -> None:
        self._tick_timer.stop()
        self._proactive_timer.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
