"""Maidie 桌宠运行期的顶层控制器与依赖编排入口。

``PetController`` 连接 PyQt 交互、Movement/Fence、Experience、Brain Session、Memory 与
配置。它负责协调生命周期和事件转发，业务判断尽量下沉到对应子系统，UI 更新留在主线程。
"""

from __future__ import annotations

import logging
import os
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from typing import Any, Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from animation.direction_manager import DirectionManager
from core.behavior import AutonomousBehaviorController, BehaviorKind
from core.experience import AttentionManager, BehaviorOrchestrator, EmotionState
from core.brain.fast_route import is_simple_time_query, is_weather_query
from core.fence import FenceController
from core.movement import Bounds, MovementController, Vec2
from core.session import AISessionCoordinator
from core.state import BehaviorPriority, PetState, StateMachine
from core.vision.intent_rules import VisionScope, detect_vision_scope


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
    facing_changed = pyqtSignal(bool)
    emotion_changed = pyqtSignal(str)
    sentence_completed = pyqtSignal(str)
    local_message_requested = pyqtSignal(str)
    fence_changed = pyqtSignal(object)
    region_selection_requested = pyqtSignal(str)
    coding_agent_event = pyqtSignal(object)
    output_event = pyqtSignal(object)
    conversation_history_cleared = pyqtSignal()

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
        self._shutting_down = False
        self.config_store = config_store
        self.action_registry = action_registry
        self.proactive_runtime = proactive_runtime
        self.state_machine = StateMachine()
        self.movement = MovementController(**(movement_options or {}))
        self.direction = DirectionManager()
        self.behavior = AutonomousBehaviorController()
        self.emotion_state = EmotionState()
        self.attention_manager = AttentionManager()
        self.behavior_orchestrator = BehaviorOrchestrator()
        self.bounds = Bounds(0, 0, 1920, 1080)
        self.fence = FenceController()
        self.drag_active = False
        self._drag_session = 0
        self._released_drag_session = -1
        self._drag_outside_logged = False
        self._drag_pause_logged = False
        self.cursor = Vec2()
        self.cursor_chase = False
        self._listeners: dict[str, list[Callable[..., None]]] = defaultdict(list)
        self._plugins: list[Any] = []
        self._selected_region_rect: tuple[int, int, int, int] | None = None
        self._user_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="maidie-user")
        self._proactive_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="maidie-proactive")
        self._memory_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="maidie-memory")
        self._memory_futures: set[Any] = set()
        self._memory_futures_lock = threading.Lock()
        self._executor = self._user_executor  # Compatibility alias.
        self._proactive_future: Any | None = None
        self._proactive_poll_timer = QTimer(self)
        self._proactive_poll_timer.setInterval(15)
        self._proactive_poll_timer.timeout.connect(self._poll_proactive_future)
        self.ai_session = AISessionCoordinator(
            ai_router, self._user_executor, self.logger,
            self._prepare_ai_request, self._show_stream_fragment,
            self._on_ai_result, self._on_ai_response_completed,
            self.sentence_completed.emit, self,
            thinking_feedback=self.message_delta.emit,
            output_event=self.output_event.emit,
        )
        self.chat_streamer = self.ai_session.streamer
        self._last_tick = monotonic()
        self._state_token = 0
        self._proactive_timer = QTimer(self)
        self._proactive_timer.timeout.connect(self._proactive_tick)
        self._proactive_timer.start(max(30, min(60, int(proactive_tick_seconds))) * 1000)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(16)

    def _wire_coding_agent(self) -> None:
        executor = getattr(self.ai_router, "executor", None)
        registry = getattr(executor, "tool_registry", None)
        tool = registry.get("coding_agent") if registry is not None else None
        if tool is None or not hasattr(tool, "set_progress_callbacks"):
            return
        tool.set_progress_callbacks(
            on_start=lambda payload: self.coding_agent_event.emit({"event": "start", **payload}),
            on_output_line=lambda payload: self.coding_agent_event.emit({"event": "output", **payload}),
            on_status_change=lambda payload: self.coding_agent_event.emit({"event": "status", **payload}),
            on_finish=lambda payload: self.coding_agent_event.emit({"event": "finish", **payload}),
        )

    def cancel_coding_agent(self) -> None:
        executor = getattr(self.ai_router, "executor", None)
        registry = getattr(executor, "tool_registry", None)
        tool = registry.get("coding_agent") if registry is not None else None
        if tool is not None and hasattr(tool, "cancel"):
            tool.cancel()

    def cancel_current_task(self) -> None:
        self.ai_session.invalidate_current_request()
        self.cancel_coding_agent()

    @property
    def state(self) -> PetState:
        return self.state_machine.state

    # Compatibility aliases while callers transition to AISessionCoordinator.
    @property
    def _busy(self) -> bool:
        return self.ai_session.busy

    @_busy.setter
    def _busy(self, value: bool) -> None:
        self.ai_session.busy = bool(value)

    @property
    def _pending_message(self) -> str:
        return self.ai_session.pending_message

    @_pending_message.setter
    def _pending_message(self, value: str) -> None:
        self.ai_session.pending_message = value

    @property
    def _pending_source(self) -> str:
        return self.ai_session.pending_source

    @_pending_source.setter
    def _pending_source(self, value: str) -> None:
        self.ai_session.pending_source = value

    @property
    def _pending_reaction(self) -> str | None:
        return self.ai_session.pending_reaction

    @_pending_reaction.setter
    def _pending_reaction(self, value: str | None) -> None:
        self.ai_session.pending_reaction = value

    @property
    def _pending_response(self) -> dict[str, str] | None:
        return self.ai_session.pending_response

    @_pending_response.setter
    def _pending_response(self, value: dict[str, str] | None) -> None:
        self.ai_session.pending_response = value

    @property
    def _request_future(self) -> Any | None:
        return self.ai_session.future

    @property
    def _request_poll_timer(self) -> QTimer:
        return self.ai_session.poll_timer

    @property
    def dominant_emotion(self) -> str:
        return self.emotion_state.get_dominant_emotion()

    def animation_for_dominant_emotion(self) -> str:
        """Translate the experience state without coupling EmotionState to UI assets."""
        return {
            "happy": "happy",
            "thinking": "waiting",
            "shy": "shy",
            "concern": "sad",
            "failed": "failed",
        }.get(self.dominant_emotion, "idle")

    def on(self, event: str, callback: Callable[..., None]) -> None:
        self._listeners[event].append(callback)

    def register_plugin(self, plugin: Any) -> None:
        self._plugins.append(plugin)

    def clear_conversation_history(self) -> bool:
        self.ai_session.invalidate_current_request()
        self._cancel_memory_extractions()
        success = bool(self.memory.delete_conversation_history())
        if not success:
            return False
        if hasattr(self.ai_router, "clear_conversation_state"):
            self.ai_router.clear_conversation_state()
        self._selected_region_rect = None
        self.conversation_history_cleared.emit()
        self._broadcast("on_conversation_history_cleared")
        return True

    def clear_long_term_memory(self) -> bool:
        self.ai_session.invalidate_current_request()
        self._cancel_memory_extractions()
        success = bool(self.memory.delete_long_term_memory())
        if success:
            self._broadcast("on_long_term_memory_cleared")
        return success

    def clear_all_memory(self) -> bool:
        self.ai_session.invalidate_current_request()
        self._cancel_memory_extractions()
        success = bool(self.memory.delete_all_memory())
        if not success:
            return False
        if hasattr(self.ai_router, "clear_conversation_state"):
            self.ai_router.clear_conversation_state()
        self._selected_region_rect = None
        self.conversation_history_cleared.emit()
        self._broadcast("on_memory_cleared")
        return True

    def clear_memory(self) -> bool:
        """Compatibility alias for the former full-memory reset."""
        return self.clear_all_memory()

    def _cancel_memory_extractions(self) -> None:
        with self._memory_futures_lock:
            futures = tuple(self._memory_futures)
        for future in futures:
            cancel = getattr(future, "cancel", None)
            if callable(cancel):
                cancel()

    def _forget_memory_future(self, future: Any) -> None:
        with self._memory_futures_lock:
            self._memory_futures.discard(future)

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
        screen_tool = self.ai_router.executor.tool_registry.get("screen")
        vision_service = getattr(screen_tool, "vision_service", None)
        if vision_service is not None and hasattr(vision_service, "reconfigure"):
            vision_service.reconfigure(config.get("vision", {}))
        coding_tool = self.ai_router.executor.tool_registry.get("coding_agent")
        if coding_tool is not None and hasattr(coding_tool, "configure"):
            coding_tool.configure(config.get("workspace", {}), config.get("coding_agent", {}))
        system_tool = self.ai_router.executor.tool_registry.get("system")
        if system_tool is not None and hasattr(system_tool, "configure"):
            system_tool.configure(config.get("workspace", {}))
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
        return {
            PetState.REACTING: "reacting",
            PetState.SLEEPING: "sleeping",
        }.get(state, state.value)

    def set_screen_bounds(self, left: float, top: float, right: float, bottom: float) -> None:
        self.bounds = Bounds(left, top, right, bottom)

    def active_bounds(self) -> Bounds:
        return self.fence.active_bounds(
            self.movement.window_width, self.movement.window_height, self.bounds
        )

    def enable_fence(self, default_width: float = 360, default_height: float = 260) -> Bounds:
        center_x = self.movement.position.x + self.movement.window_width / 2
        center_y = self.movement.position.y + self.movement.window_height / 2
        rect = self.fence.enable_default(
            center_x, center_y, self.bounds,
            self.movement.window_width, self.movement.window_height,
            default_width, default_height,
        )
        self.movement.stop()
        x, y = self.fence.clamp_point(
            self.movement.position.x, self.movement.position.y,
            self.movement.window_width, self.movement.window_height,
        )
        self.sync_geometry(x, y, self.movement.window_width, self.movement.window_height)
        self.position_requested.emit(x, y)
        self.behavior.postpone(1.0)
        self._emit_fence_feedback("fence_enabled", "shy")
        self._log_fence("fence_enabled", rect=rect)
        self.fence_changed.emit(rect)
        return rect

    def disable_fence(self) -> None:
        was_enabled = self.fence.is_enabled()
        self.fence.disable()
        self.behavior.postpone(1.0)
        if was_enabled:
            self.fence_changed.emit(None)
            self._emit_fence_feedback("fence_disabled", "celebrate")
            self._log_fence("fence_disabled")

    def update_fence_rect(self, rect: Any) -> Bounds | None:
        """Apply a user-edited fence rectangle and keep it inside the screen."""
        if not self.fence.is_enabled():
            return None
        if isinstance(rect, Bounds):
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        elif hasattr(rect, "x") and hasattr(rect, "width"):
            left, top = float(rect.x()), float(rect.y())
            right, bottom = left + float(rect.width()), top + float(rect.height())
        else:
            left, top, right, bottom = map(float, rect)
        min_width = self.movement.window_width + self.fence.padding * 2
        min_height = self.movement.window_height + self.fence.padding * 2
        width = min(max(abs(right - left), min_width), self.bounds.right - self.bounds.left)
        height = min(max(abs(bottom - top), min_height), self.bounds.bottom - self.bounds.top)
        left = max(self.bounds.left, min(self.bounds.right - width, min(left, right)))
        top = max(self.bounds.top, min(self.bounds.bottom - height, min(top, bottom)))
        final_rect = Bounds(left, top, left + width, top + height)
        self.fence.enable(final_rect)
        x, y = self.fence.clamp_point(
            self.movement.position.x, self.movement.position.y,
            self.movement.window_width, self.movement.window_height,
        )
        if (x, y) != (self.movement.position.x, self.movement.position.y):
            self.sync_geometry(x, y, self.movement.window_width, self.movement.window_height)
            self.position_requested.emit(x, y)
        self.fence_changed.emit(final_rect)
        return final_rect

    def _emit_fence_feedback(self, event: str, action: str) -> None:
        text = self.fence.dialogues.get(event)
        self._log_fence("fence_dialogue_event", dialogue_event=event)
        self._log_fence("fence_dialogue_selected", dialogue=text)
        if self.fence.dialogues.last_avoided_repeat:
            self._log_fence("fence_dialogue_avoid_repeat", dialogue_event=event)
        self.local_message_requested.emit(text)
        if not self._play_action(action, force=True):
            animation = "happy" if event == "fence_disabled" else "reacting"
            self.set_state(PetState.REACTING, BehaviorPriority.USER_CLICK, 700,
                           force=True, animation=animation)

    def _log_fence(self, event: str, **fields: Any) -> None:
        try:
            details = " ".join(f"{key}={value}" for key, value in fields.items())
            self.logger.debug("%s%s", event, f" {details}" if details else "")
        except Exception:
            pass

    def on_pet_drag_started(self) -> None:
        self.drag_active = True
        self._drag_session += 1
        self._drag_outside_logged = False
        self._drag_pause_logged = False
        self.movement.stop()
        self._log_fence("fence_drag_started", drag_session=self._drag_session)

    def on_pet_drag_moved(self, x: float, y: float, width: float, height: float) -> None:
        if not self.drag_active:
            return
        self.sync_geometry(x, y, width, height)
        if (self.fence.is_enabled()
                and not self.fence.contains_pet(x, y, width, height)
                and not self._drag_outside_logged):
            self._drag_outside_logged = True
            self._log_fence("fence_drag_moving_outside", x=x, y=y)

    def on_pet_drag_cancelled(self) -> None:
        self.drag_active = False

    def sync_geometry(self, x: float, y: float, width: float, height: float) -> None:
        self.movement.sync_geometry(x, y, width, height)

    def on_pet_dragged(
        self, x: float, y: float, width: float, height: float, drag_dx: float = 0.0
    ) -> None:
        if (self._drag_session > 0 and not self.drag_active
                and self._released_drag_session == self._drag_session):
            return
        if self.drag_active and self._released_drag_session == self._drag_session:
            return
        if self.drag_active:
            self._released_drag_session = self._drag_session
        self.drag_active = False
        self.movement.stop()
        was_outside = self.fence.is_enabled() and not self.fence.contains_pet(
            x, y, width, height
        )
        x, y = self.fence.nearest_inside_position(x, y, width, height)
        self.sync_geometry(x, y, width, height)
        if was_outside:
            self._log_fence("fence_drag_released_outside")
            self._log_fence("fence_snapback_target", x=x, y=y)
            self.position_requested.emit(x, y)
        else:
            self._log_fence("fence_drag_released_inside")
        previous_facing = self.direction.facing_right
        facing_right = self.direction.update_direction(drag_dx)
        if facing_right != previous_facing:
            self.facing_changed.emit(facing_right)
        self.behavior.postpone(0.3 if was_outside else 2.5)
        if was_outside and self.fence.should_complain():
            self._emit_fence_feedback("fence_snapback", "shy")
            return
        if was_outside:
            self._log_fence("fence_complain_suppressed_by_cooldown")
            return
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
        self.emotion_state.apply_event("headpat")
        self.emotion_changed.emit(self.emotion_state.get_dominant_emotion())
        self._play_action("headpat")

    def on_facepoke(self) -> None:
        self.movement.stop()
        self._broadcast("on_facepoke")
        self.emotion_state.apply_event("facepoke")
        self.emotion_changed.emit(self.emotion_state.get_dominant_emotion())
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
        """把用户或 Proactive 文本提交给唯一 AISessionCoordinator。

        UI 线程只处理 busy/框选等即时门控；实际 Router/LLM/Tool 工作由 Session 提交到
        后台 Executor。selected-region 请求先完成显式框选，避免在未获范围时截图。
        """
        if getattr(self, "_shutting_down", False):
            return
        if self.ai_session.busy:
            if not proactive:
                self.local_message_requested.emit("我还在分析上一个任务，完成后再告诉我吧。")
            return
        if not proactive and detect_vision_scope(message) is VisionScope.SELECTED_REGION:
            if not self.ai_session.busy:
                self.local_message_requested.emit("好，你框一下要我看的地方就行。")
                self.region_selection_requested.emit(message)
            return
        self.ai_session.submit(message, proactive)

    def complete_region_selection(self, message: str,
                                  rect: tuple[int, int, int, int]) -> None:
        """保存本次显式框选坐标，并继续原先暂停的 AI 请求。"""
        if getattr(self, "_shutting_down", False):
            return
        self._selected_region_rect = rect
        self.ai_session.submit(message, False)

    def cancel_region_selection(self) -> None:
        if getattr(self, "_shutting_down", False):
            return
        self._selected_region_rect = None
        self.local_message_requested.emit("好，那这次我就不看屏幕啦。")

    def _prepare_ai_request(self, message: str, proactive: bool) -> tuple[list[dict[str, Any]], str | None]:
        # Intent routing performs an API request. Keep it inside the worker's
        # normal BrainRouter flow instead of blocking the Qt event loop here
        # (and routing the same message a second time in ask_stream()).
        pending_reaction = (
            self.action_registry.match_message(message) if self.action_registry else None
        )
        self.stream_started.emit({"source": "chat"})
        self.emotion_state.apply_event("ai_thinking")
        self.emotion_changed.emit("thinking")
        self.movement.stop()
        target_state = PetState.REMINDING if proactive else PetState.THINKING
        target_priority = BehaviorPriority.PROACTIVE if proactive else BehaviorPriority.AI_TALKING
        self.set_state(target_state, target_priority, 400, force=True,
                       animation="happy" if proactive else None)
        # Session 历史、Attention 和一次性框选坐标在此汇合，再作为显式 context 进入 Brain。
        context = self.memory.get_recent()
        if self._selected_region_rect is not None:
            context.append({"vision_selected_rect": self._selected_region_rect,
                            "event_type": "internal"})
            self._selected_region_rect = None
        if re.search(r"(?:搜|搜索|查).*(?:剪贴板|刚复制)", message, re.I):
            try:
                from PyQt6.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard_text = clipboard.text().strip() if clipboard else ""
                if clipboard_text:
                    context.append({"clipboard": clipboard_text, "event_type": "internal"})
            except Exception:
                self.logger.debug("Clipboard text unavailable for explicit search", exc_info=True)
        memory_context = self.memory.prompt_context() if hasattr(self.memory, "prompt_context") else ""
        if memory_context:
            context.append({"memory": memory_context})
        self._refresh_attention()
        attention_context = self.attention_manager.context_for(message)
        if attention_context:
            context.append(attention_context)
        return context, pending_reaction

    def _handle_stream_delta(self, delta: str) -> None:
        self.ai_session.handle_stream_delta(delta)

    def _present_stream_text(self, fragment: str) -> None:
        self.ai_session.present_stream_text(fragment)

    def _show_stream_fragment(self, fragment: str) -> None:
        if self.state != PetState.TALKING:
            self.set_state(
                PetState.TALKING,
                BehaviorPriority.AI_TALKING,
                force=True,
                animation="talking",
            )
            self.emotion_changed.emit("speaking")
        self.message_delta.emit(fragment)

    def _poll_request(self) -> None:
        self.ai_session.poll_future()

    def _handle_result(self, result: dict[str, Any]) -> None:
        self.ai_session.handle_result(result)

    def _on_ai_result(self, response: dict[str, str], failed: bool,
                      error_message: str | None) -> None:
        if failed and error_message is not None:
            self.request_failed.emit(error_message)
            self.emotion_state.apply_event("tool_failure")
        if not failed:
            event = "tool_success" if response["source"] not in {"chat", "codex"} else "ai_reply"
            self.emotion_state.apply_event(event, response["emotion"])

    def _complete_stream_response(self) -> None:
        self.ai_session.complete_stream_response()

    def _on_ai_response_completed(self, message: str, response: dict[str, Any],
                                  pending_reaction: str | None) -> None:
        if pending_reaction:
            animation = pending_reaction
        elif response["source"] == "codex":
            animation = "review"
        elif response["emotion"] in ("happy", "excited"):
            animation = "happy"
        elif response["emotion"] == "sad":
            animation = "failed"
        else:
            animation = "idle"
        duration = min(9000, max(2800, len(response["text"]) * 90))
        self.emotion_changed.emit(response["emotion"])
        if animation == "idle":
            self.set_state(PetState.IDLE, BehaviorPriority.IDLE, force=True)
        else:
            final_state = PetState.THINKING if response["source"] == "codex" else PetState.REACTING
            self.set_state(
                final_state,
                BehaviorPriority.AI_TALKING,
                850,
                force=True,
                animation=animation,
            )
            token = self._state_token
            QTimer.singleShot(900, lambda: self._recover_if_current(token))
        self.message_received.emit(response)
        internal_event = bool(self.ai_session.pending_proactive)
        stored_response = str(response.get("full_text") or response["text"])
        if not internal_event:
            self.memory.save(message, stored_response)
        should_extract = self._should_extract_memory(message, response)
        if (
            should_extract and not internal_event
            and hasattr(self.memory, "save_extracted")
            and hasattr(self.ai_router, "extract_memories")
            and (
                not hasattr(self.memory, "can_extract")
                or self.memory.can_extract(message, response["text"])
            )
        ):
            generation = (
                self.memory.generation_token()
                if hasattr(self.memory, "generation_token") else None
            )
            # Memory 抽取是请求完成后的异步旁路，不能阻塞气泡完成或 Qt 主线程。
            future = self._memory_executor.submit(
                self._extract_and_store_memories,
                message,
                stored_response,
                generation,
            )
            with self._memory_futures_lock:
                self._memory_futures.add(future)
            add_done_callback = getattr(future, "add_done_callback", None)
            if callable(add_done_callback):
                add_done_callback(self._forget_memory_future)
        elif not should_extract:
            try:
                self.logger.debug("performance memory_extraction_skipped=true request_id=%s",
                                  self.ai_session.request_id)
            except Exception:
                pass
        self._broadcast("on_message", response)

    @staticmethod
    def _should_extract_memory(message: str, response: dict[str, str]) -> bool:
        text = message.strip()
        if is_simple_time_query(text) or is_weather_query(text):
            return False
        if re.fullmatch(r"(?:你好|嗨|hello|hi|嗯|好的)[！!。.？?\s]*", text, re.I):
            return False
        if response.get("source") in {"tool", "screen"}:
            return False
        return True

    def _extract_and_store_memories(
        self, message: str, response: str, generation: int | None = None
    ) -> None:
        started = monotonic()
        try:
            extracted = self.ai_router.extract_memories(message, response)
            if generation is None:
                self.memory.save_extracted(extracted)
            else:
                self.memory.save_extracted(extracted, generation=generation)
        except Exception:
            self.logger.exception("Memory extraction failed")
        finally:
            try:
                self.logger.debug("performance memory_extraction_duration_ms=%.3f thread_name=%s",
                                  (monotonic() - started) * 1000,
                                  threading.current_thread().name)
            except Exception:
                pass

    def _activate_talking(self, animation: str, duration: int) -> None:
        if self._shutting_down:
            return
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
        if self._shutting_down:
            return
        if self._busy:
            self.set_state(PetState.THINKING, BehaviorPriority.AI_TALKING, 300)
        else:
            self._recover_if_current(self._state_token)

    def _recover_if_current(self, token: int) -> None:
        if self._shutting_down:
            return
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
        if self._shutting_down:
            return
        now = monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        if self.drag_active:
            if not self._drag_pause_logged:
                self._drag_pause_logged = True
                self._log_fence("movement_paused_for_drag")
                if self.fence.is_enabled():
                    self._log_fence("fence_clamp_skipped_during_drag")
            return

        active_bounds = self.active_bounds()
        if not self._busy and self.state_machine.can_interrupt(BehaviorPriority.AUTONOMOUS):
            intent = self.behavior.decide(
                active_bounds,
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
        position = self.movement.tick(dt, active_bounds)
        previous_facing = self.direction.facing_right
        facing_right = self.direction.update_direction(position.x - old_position.x)
        if facing_right != previous_facing:
            self.facing_changed.emit(facing_right)
        if position.distance_to(old_position) > 0.01:
            self.position_requested.emit(position.x, position.y)

        motion_state = self.movement.classify_state()
        if self.state_machine.can_interrupt(BehaviorPriority.AUTONOMOUS):
            priority = BehaviorPriority.AUTONOMOUS if motion_state != PetState.IDLE else BehaviorPriority.IDLE
            self.set_state(motion_state, priority)

    def _proactive_tick(self) -> None:
        if self._shutting_down:
            return
        if (not self.proactive_runtime or not self.proactive_runtime.engine.enabled
                or self._busy):
            return
        if self._proactive_future is not None and not self._proactive_future.done():
            return
        self._proactive_future = self._proactive_executor.submit(self.proactive_runtime.tick)
        self._proactive_poll_timer.start()

    def _poll_proactive_future(self) -> None:
        if self._shutting_down:
            return
        future = self._proactive_future
        if future is None or not future.done():
            return
        self._proactive_poll_timer.stop()
        self._proactive_future = None
        try:
            result = future.result()
        except Exception:
            self.logger.exception("Proactive Agent tick failed")
            return
        self._complete_proactive_result(result)

    def _complete_proactive_result(self, result: tuple[dict[str, Any], Any]) -> None:
        """Apply a worker result from the Qt-thread polling entry point."""
        if self._shutting_down or self._busy or not self.proactive_runtime:
            return
        context, decision = result
        self.attention_manager.update(context)
        experience_decision = self.behavior_orchestrator.decide(
            self.attention_manager.state,
            self.emotion_state.get_dominant_emotion(),
            float(context.get("idle_time", 0)),
            str(context.get("window_title", "")),
        )
        if experience_decision:
            self._broadcast("on_behavior_decision", experience_decision)
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

    def _refresh_attention(self) -> None:
        if self._shutting_down:
            return
        """Refresh cheap foreground facts; OCR remains on the existing awareness cadence."""
        if not self.proactive_runtime:
            return
        awareness = self.proactive_runtime.awareness
        context: dict[str, Any] = {}
        try:
            context.update(awareness.window_tracker.snapshot())
            if awareness.app_tracker:
                context.update(awareness.app_tracker.snapshot())
            screen_reader = getattr(awareness, "screen_reader", None)
            cached = getattr(screen_reader, "_last_result", None)
            if isinstance(cached, dict):
                context["screen"] = dict(cached)
            self.attention_manager.update(context)
        except Exception:
            self.logger.exception("Attention refresh failed")

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.cancel_coding_agent()
        self.logger.info("Shutting down Maidie controller...")
        self._tick_timer.stop()
        self.logger.info("Stopped pet tick timer")
        self._proactive_timer.stop()
        self._proactive_poll_timer.stop()
        self.logger.info("Stopped proactive timers")
        self.ai_session.shutdown()
        self.logger.info("Stopped agent polling timer")
        if self._proactive_future is not None:
            cancel = getattr(self._proactive_future, "cancel", None)
            if callable(cancel):
                cancel()
            self._proactive_future = None
        self._user_executor.shutdown(wait=False, cancel_futures=True)
        self._proactive_executor.shutdown(wait=False, cancel_futures=True)
        self._cancel_memory_extractions()
        self._memory_executor.shutdown(wait=False, cancel_futures=True)
        self.logger.info("Maidie controller shutdown complete")
