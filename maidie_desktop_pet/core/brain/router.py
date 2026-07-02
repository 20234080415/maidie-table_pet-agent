from __future__ import annotations

import re
from time import monotonic
from typing import Any, Callable

from core.brain.executor import BrainExecutor
from core.brain.intent_classifier import IntentClassifier
from core.brain.llm_router import LLMIntentRouter
from core.brain.planner import BrainPlanner
from core.brain.synthesizer import Synthesizer
from core.performance import mark


class BrainRouter:
    """Maidie Core Brain V4: the sole production gate for chat and tools."""

    TECHNICAL = re.compile(r"\b(code|error|debug|api|database|git|python|javascript|docker)\b|代码|报错|调试|架构", re.I)
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

    def classify(self, user_input: str) -> str:
        return self.intent_router.classify(user_input)

    def route(self, user_input: str, context: list[dict[str, Any]] | None = None,
              on_delta: Callable[[str], None] | None = None) -> dict[str, str]:
        context = context or []
        started = monotonic()
        try:
            intent = self.intent_router.classify(user_input, context)
        finally:
            route = self.intent_router.last_route or {}
            mark(route_intent=str(route.get("intent", "unknown")),
                 route_source=str(route.get("route_source", route.get("source", "unknown"))),
                 route_duration_ms=round((monotonic() - started) * 1000, 3))
        if intent in {"task", "screen", "code_task", "system_task"}:
            attention = next((item.get("attention") for item in reversed(context)
                              if isinstance(item, dict) and "attention" in item), None)
            started = monotonic()
            try:
                plan = self.planner.plan_for_intent(user_input, intent, self.memory, attention)
            finally:
                mark(plan_duration_ms=round((monotonic() - started) * 1000, 3))
            executions = self.executor.execute(plan, user_input)
            source = self._source_for_intent(intent)
            started = monotonic()
            try:
                result = self.synthesizer.synthesize(
                    user_input, source, plan, executions, self._memory_context(), context, on_delta,
                    technical=self._is_technical(source, user_input),
                )
            finally:
                mark(synthesize_duration_ms=round((monotonic() - started) * 1000, 3))
            return result
        started = monotonic()
        try:
            result = self.synthesizer.synthesize(
                user_input, "chat", None, [], self._memory_context(), context, on_delta,
                technical=self._is_technical(intent, user_input),
            )
        finally:
            mark(synthesize_duration_ms=round((monotonic() - started) * 1000, 3))
        return result

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
