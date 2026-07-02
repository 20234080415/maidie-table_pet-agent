from __future__ import annotations

import re
from typing import Any, Callable

from core.brain.intent_classifier import IntentClassifier
from core.brain.llm_router import LLMIntentRouter
from core.brain.planner import BrainPlanner
from core.brain.synthesizer import Synthesizer


class BrainRouter:
    """Maidie Core Brain V4: the sole production gate for chat and tools."""

    TECHNICAL = re.compile(r"\b(code|error|debug|api|database|git|python|javascript|docker)\b|代码|报错|调试|架构", re.I)
    ALLOWED_TOOLS = {"weather", "time", "search", "screen", "memory", "system", "codex", "opencode"}

    def __init__(self, chat_client: Any, codex_client: Any, tool_registry: Any, memory: Any,
                 classifier: IntentClassifier | None = None, planner: BrainPlanner | None = None,
                 synthesizer: Synthesizer | None = None,
                 intent_router: LLMIntentRouter | None = None) -> None:
        self.chat_client, self.codex_client = chat_client, codex_client
        self.tool_registry, self.memory = tool_registry, memory
        self.classifier = classifier or IntentClassifier()
        self.intent_router = intent_router or LLMIntentRouter(chat_client, self.classifier)
        self.planner = planner or BrainPlanner()
        self.synthesizer = synthesizer or Synthesizer(chat_client, codex_client)

    def classify(self, user_input: str) -> str:
        return self.intent_router.classify(user_input)

    def route(self, user_input: str, context: list[dict[str, Any]] | None = None,
              on_delta: Callable[[str], None] | None = None) -> dict[str, str]:
        context = context or []
        intent = self.intent_router.classify(user_input, context)
        if intent in {"task", "screen", "code_task", "system_task"}:
            attention = next((item.get("attention") for item in reversed(context)
                              if isinstance(item, dict) and "attention" in item), None)
            plan = self.planner.plan_for_intent(user_input, intent, self.memory, attention)
            return self._run_plan(user_input, self._source_for_intent(intent), plan, context, on_delta)
        return self.synthesizer.synthesize(
            user_input, "chat", None, [], self._memory_context(), context, on_delta,
            technical=self._is_technical(intent, user_input),
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

    def _run_plan(self, user_input: str, source: str, plan: dict[str, Any],
                  context: list[dict[str, Any]], on_delta: Callable[[str], None] | None) -> dict[str, str]:
        executions = []
        for index, step in enumerate(plan.get("steps", [])):
            tool_name = str(step.get("tool", ""))
            params = step.get("params", {}) if isinstance(step.get("params"), dict) else {}
            if tool_name not in self.ALLOWED_TOOLS:
                result = {"type": tool_name, "raw": {"error": "tool blocked by router"}, "source": "local"}
            else:
                result = self._execute_tool(tool_name, user_input, params)
            result.pop("text", None)
            executions.append({"index": index, "tool": tool_name,
                               "ok": not bool(result.get("raw", {}).get("error")), "data": result})
        return self.synthesizer.synthesize(
            user_input, source, plan, executions, self._memory_context(), context, on_delta,
            technical=self._is_technical(source, user_input),
        )

    def _execute_tool(self, name: str, user_input: str, params: dict[str, Any]) -> dict[str, Any]:
        tool = self.tool_registry.get(name)
        if tool is None:
            return {"type": name, "raw": {"error": f"{name} unavailable"}, "source": "local"}
        # Plan parameters are untrusted data, never proof of user authorization.
        params = dict(params)
        params.pop("confirmed", None)
        try:
            if name == "system" and hasattr(tool, "execute"):
                operation = str(params.get("operation") or params.get("action") or "")
                if operation:
                    return tool.execute(operation, params)
            if name == "memory":
                return tool.run(user_input, kind=str(params.get("kind", "long_term")),
                                limit=int(params.get("limit", 20)))
            return tool.run(str(params.get("query") or user_input))
        except Exception as exc:
            return {"type": name, "raw": {"error": str(exc)}, "source": "local"}

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
