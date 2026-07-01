from __future__ import annotations

import re
from typing import Any, Callable

from core.brain.intent_classifier import IntentClassifier
from core.brain.planner import BrainPlanner
from core.brain.synthesizer import Synthesizer


class BrainRouter:
    """Maidie Core Brain V4: the sole production gate for chat and tools."""

    TECHNICAL = re.compile(r"\b(code|error|debug|api|database|git|python|javascript|docker)\b|代码|报错|调试|架构", re.I)
    ALLOWED_TOOLS = {"weather", "time", "search", "screen", "memory"}

    def __init__(self, chat_client: Any, codex_client: Any, tool_registry: Any, memory: Any,
                 classifier: IntentClassifier | None = None, planner: BrainPlanner | None = None,
                 synthesizer: Synthesizer | None = None) -> None:
        self.chat_client, self.codex_client = chat_client, codex_client
        self.tool_registry, self.memory = tool_registry, memory
        self.classifier = classifier or IntentClassifier()
        self.planner = planner or BrainPlanner()
        self.synthesizer = synthesizer or Synthesizer(chat_client, codex_client)

    def classify(self, user_input: str) -> str:
        return self.classifier.classify(user_input)

    def route(self, user_input: str, context: list[dict[str, Any]] | None = None,
              on_delta: Callable[[str], None] | None = None) -> dict[str, str]:
        intent = self.classify(user_input)
        context = context or []
        if intent == "screen":
            plan = self.planner.screen_plan(user_input)
            return self._run_plan(user_input, "screen", plan, context, on_delta)
        if intent == "task":
            plan = self.planner.plan(user_input, self.memory)
            return self._run_plan(user_input, "tool", plan, context, on_delta)
        return self.synthesizer.synthesize(
            user_input, "chat", None, [], self._memory_context(), context, on_delta,
            technical=bool(self.TECHNICAL.search(user_input)),
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
            technical=bool(self.TECHNICAL.search(user_input)),
        )

    def _execute_tool(self, name: str, user_input: str, params: dict[str, Any]) -> dict[str, Any]:
        tool = self.tool_registry.get(name)
        if tool is None:
            return {"type": name, "raw": {"error": f"{name} unavailable"}, "source": "local"}
        try:
            if name == "memory":
                return tool.run(user_input, kind=str(params.get("kind", "long_term")),
                                limit=int(params.get("limit", 20)))
            return tool.run(str(params.get("query") or user_input))
        except Exception as exc:
            return {"type": name, "raw": {"error": str(exc)}, "source": "local"}

    def _memory_context(self) -> str:
        try:
            return str(self.memory.prompt_context())
        except Exception:
            return ""
