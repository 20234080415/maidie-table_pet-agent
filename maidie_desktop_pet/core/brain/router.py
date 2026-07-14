from __future__ import annotations

import logging
import re
from time import monotonic
from typing import Any, Callable

from core.brain.executor import BrainExecutor
from core.brain.intent_classifier import IntentClassifier
from core.brain.llm_router import LLMIntentRouter
from core.brain.planner import BrainPlanner
from core.brain.synthesizer import Synthesizer
from core.session.output_events import OutputMode
from core.performance import mark
from core.vision.vision_session import VisionSession
from core.vision.intent_rules import detect_vision_scope


class BrainRouter:
    """Maidie Core Brain V4: the sole production gate for chat and tools."""

    TECHNICAL = re.compile(r"\b(code|error|debug|api|database|git|python|javascript|docker)\b|代码|报错|调试|架构", re.I)
    VISION_FOLLOW_UP = re.compile(
        r"^(?:那怎么办|然后呢|我该改哪里|这个命令在哪输入|还有别的方法吗|如果不行呢|"
        r"为什么会这样|怎么修)[？?！!。.\s]*$", re.I,
    )
    VISION_REFRESH = re.compile(
        r"(?:重新看|再看一下屏幕|重新截图|现在呢|刷新一下)", re.I,
    )
    VISION_CLEAR = re.compile(r"^(?:不用看了|清除上下文)[？?！!。.\s]*$", re.I)
    VISION_CONFIRM = re.compile(r"^(?:嗯|对|是|看一下|你看|可以)[？?！!。.\s]*$", re.I)
    def __init__(self, chat_client: Any, codex_client: Any, tool_registry: Any, memory: Any,
                 classifier: IntentClassifier | None = None, planner: BrainPlanner | None = None,
                 synthesizer: Synthesizer | None = None,
                 intent_router: LLMIntentRouter | None = None,
                 executor: BrainExecutor | None = None) -> None:
        self.chat_client, self.codex_client = chat_client, codex_client
        self.memory = memory
        self.classifier = classifier or IntentClassifier()
        self.intent_router = intent_router or LLMIntentRouter(chat_client, self.classifier)
        self.planner = planner or BrainPlanner()
        self.executor = executor or BrainExecutor(tool_registry)
        self.synthesizer = synthesizer or Synthesizer(chat_client, codex_client)
        self._vision_clarification_pending = False
        self._vision_clarification_created_at = 0.0
        self._vision_pending_default_scope = "active_window"
        self.logger = logging.getLogger(__name__)

    def classify(self, user_input: str) -> str:
        return self.intent_router.classify(user_input)

    def clear_conversation_state(self) -> None:
        if hasattr(self.intent_router, "clear_context"):
            self.intent_router.clear_context()
        service = self._vision_service()
        if service is not None and hasattr(service, "clear_session"):
            service.clear_session()
        self._vision_clarification_pending = False
        self._vision_clarification_created_at = 0.0
        self._vision_pending_default_scope = "active_window"

    def route(self, user_input: str, context: list[dict[str, Any]] | None = None,
              on_delta: Callable[[str], None] | None = None) -> dict[str, str]:
        context = context or []
        total_started = monotonic()
        session = self._vision_session()
        if self.VISION_CLEAR.fullmatch(user_input.strip()):
            service = self._vision_service()
            if service is not None and hasattr(service, "clear_session"):
                service.clear_session()
            elif session is not None:
                session.clear()
            self._vision_clarification_pending = False
            result = self.synthesizer.synthesize(
                user_input, "vision_cleared", None, [], self._memory_context(), context, on_delta,
                output_mode=(OutputMode.CHAT_NATURAL if on_delta else None),
            )
            self._log_vision_route("vision_clear", "fast_rule", session, False,
                                   "active_window", total_started, 0.0)
            return result

        if (self._vision_clarification_pending and
                monotonic() - self._vision_clarification_created_at > 60):
            self._vision_clarification_pending = False
        confirmed = (self._vision_clarification_pending and
                     bool(self.VISION_CONFIRM.fullmatch(user_input.strip())))
        started = monotonic()
        try:
            if confirmed:
                intent = "screen"
                self.intent_router.last_route = {
                    "intent": "vision", "confidence": 1.0, "source": "clarification_confirm",
                    "route_source": "clarification_confirm", "need_screen": True,
                    "need_vision": True, "vision_scope": "active_window",
                }
            else:
                intent = self.intent_router.classify(user_input, context)
        finally:
            candidate_route = self.intent_router.last_route
            route = candidate_route if isinstance(candidate_route, dict) else {}
            mark(route_intent=str(route.get("intent", "unknown")),
                 route_source=str(route.get("route_source", route.get("source", "unknown"))),
                 route_duration_ms=round((monotonic() - started) * 1000, 3))
        active_session = bool(session and session.has_active_session())
        follow_up = bool(active_session and self.VISION_FOLLOW_UP.fullmatch(user_input.strip()))
        refresh_requested = bool(active_session and self.VISION_REFRESH.search(user_input))
        if follow_up:
            intent = "screen"
            route = {"intent": "vision_follow_up", "route_source": "vision_session",
                     "source": "vision_session", "vision_scope": session.scope}
        elif refresh_requested:
            intent = "screen"
            route = {"intent": "vision_refresh", "route_source": "vision_refresh",
                     "source": "vision_refresh", "vision_scope": session.scope}
        if intent == "clarification":
            self._vision_clarification_pending = True
            self._vision_clarification_created_at = monotonic()
            service = self._vision_service()
            self._vision_pending_default_scope = str(
                getattr(service, "default_scope", "active_window")
            )
        else:
            self._vision_clarification_pending = False
        if intent in {"task", "vision", "screen", "code_task", "system_task"}:
            attention = next((item.get("attention") for item in reversed(context)
                              if isinstance(item, dict) and "attention" in item), None)
            started = monotonic()
            try:
                if route.get("task_type") not in {None, "", "none"}:
                    plan = self.planner.plan_route(user_input, route)
                    plan = self.planner._with_attention(plan, attention)
                else:
                    plan = self.planner.plan_for_intent(user_input, intent, self.memory, attention)
                if intent in {"vision", "screen"}:
                    service = self._vision_service()
                    configured_default = str(getattr(service, "default_scope", "active_window"))
                    default_scope = (self._vision_pending_default_scope if confirmed else
                                     str(route.get("vision_scope") or configured_default))
                    scope = (session.scope if follow_up and session is not None else
                             detect_vision_scope(user_input, default_scope).value)
                    selected_rect = next((item.get("vision_selected_rect")
                                          for item in reversed(context)
                                          if isinstance(item, dict)
                                          and item.get("vision_selected_rect")), None)
                    force_refresh = bool(self.VISION_REFRESH.search(user_input))
                    for step in plan.get("steps", []):
                        if isinstance(step, dict) and step.get("tool") == "screen":
                            params = step.setdefault("params", {})
                            params.update({"scope": scope, "reuse_session": follow_up,
                                           "force_refresh": force_refresh,
                                           "selected_rect": selected_rect})
            finally:
                mark(plan_duration_ms=round((monotonic() - started) * 1000, 3))
            executions = (
                self.executor.execute(plan, user_input, on_event=on_delta)
                if on_delta else self.executor.execute(plan, user_input)
            )
            source = self._source_for_intent(intent)
            started = monotonic()
            try:
                result = self.synthesizer.synthesize(
                    user_input, source, plan, executions, self._memory_context(), context, on_delta,
                    technical=self._is_technical(source, user_input),
                    output_mode=(OutputMode.TASK_STREAM if on_delta else None),
                )
            finally:
                deepseek_latency = monotonic() - started
                mark(synthesize_duration_ms=round(deepseek_latency * 1000, 3))
            if session is not None and session.has_active_session() and session.get_context():
                session.update(session.get_context(), user_input, result.get("text"),
                               scope=scope if intent in {"vision", "screen"} else session.scope)
            self._log_vision_route(str(route.get("intent", intent)),
                                   str(route.get("route_source", route.get("source", "unknown"))),
                                   session, follow_up, scope if intent in {"vision", "screen"}
                                   else "active_window", total_started, deepseek_latency)
            return result
        started = monotonic()
        try:
            if intent == "clarification":
                result = self.synthesizer.synthesize(
                    user_input, "clarification", None, [], self._memory_context(), context,
                    on_delta, output_mode=(OutputMode.CHAT_NATURAL if on_delta else None),
                )
                self._log_vision_route("clarification",
                                       str(route.get("route_source", "fast_rule")), session,
                                       False, "active_window", total_started, 0.0)
                return result
            result = self.synthesizer.synthesize(
                user_input, "chat", None, [], self._memory_context(), context, on_delta,
                technical=self._is_technical(intent, user_input),
                output_mode=(OutputMode.CHAT_NATURAL if on_delta else None),
            )
        finally:
            mark(synthesize_duration_ms=round((monotonic() - started) * 1000, 3))
        return result

    def _vision_session(self) -> Any:
        service = self._vision_service()
        session = getattr(service, "session", None)
        return session if isinstance(session, VisionSession) else None

    def _vision_service(self) -> Any:
        try:
            tool = self.executor.tool_registry.get("screen")
            return getattr(tool, "vision_service", None)
        except Exception:
            return None

    def _log_vision_route(self, intent: str, source: str, session: Any,
                          session_hit: bool, scope: str, total_started: float,
                          deepseek_latency: float) -> None:
        age = session.age() if session is not None else None
        self.logger.info(
            "vision_route route_source=%s route_intent=%s vision_session_hit=%s "
            "vision_session_age=%s vision_scope=%s clarification_pending=%s "
            "deepseek_latency=%.3f total_latency=%.3f",
            source, intent, str(session_hit).lower(),
            "none" if age is None else f"{age:.3f}", scope,
            str(self._vision_clarification_pending).lower(), deepseek_latency,
            monotonic() - total_started,
        )

    def ask(self, prompt: str, context: list[dict[str, Any]]) -> dict[str, str]:
        return self.route(prompt, context)

    def ask_stream(self, prompt: str, context: list[dict[str, Any]],
                   on_delta: Callable[[str], None]) -> dict[str, str]:
        return self.route(prompt, context, on_delta)

    def extract_memories(self, message: str, response: str) -> dict[str, list[Any]]:
        try:
            return self.chat_client.extract_memories(message, response)
        except Exception:
            return {"facts": [], "preferences": []}

    @staticmethod
    def _source_for_intent(intent: str) -> str:
        return {
            "vision": "screen",
            "screen": "screen",
            "code_task": "code_task",
            "system_task": "system_task",
        }.get(intent, "tool")

    def _is_technical(self, intent: str, user_input: str) -> bool:
        return intent == "code_task" or bool(self.TECHNICAL.search(user_input))

    def _memory_context(self) -> str:
        try:
            return str(self.memory.prompt_context())
        except Exception:
            return ""
