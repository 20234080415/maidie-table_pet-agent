from __future__ import annotations

import re
from typing import Any, Callable

from ai.client import AIClient, AIResponse, normalize_response
from ai.prompt import inject_capability_context
from core.agent.intent import Intent


class AIRouter:
    """Agent Router V2: classify first; facts and decisions use the agent pipeline."""

    TECHNICAL_PATTERN = re.compile(r"\b(code|error|debug|api|database|git|python|javascript|docker)\b|代码|报错|调试|架构", re.I)

    def __init__(self, chat_client: AIClient, codex_client: AIClient, network_plugin: Any | None = None,
                 tool_registry: Any | None = None, agent_core: Any | None = None):
        self.chat_client, self.codex_client = chat_client, codex_client
        self.network_plugin, self.tool_registry, self.agent_core = network_plugin, tool_registry, agent_core

    def classify(self, text: str) -> str:
        if self.agent_core and self.agent_core.detector.is_screen_related(text):
            return Intent.SCREEN_AWARENESS.value
        if self.TECHNICAL_PATTERN.search(text):
            return "codex"
        if self.agent_core:
            return self.agent_core.detect_intent(text)
        if self.tool_registry and self.tool_registry.match(text):
            return Intent.DIRECT_TOOL.value
        if self.network_plugin and self.network_plugin.should_handle(text):
            return "search"
        return "chat"

    def extract_memories(self, message: str, response: str) -> dict[str, list[Any]]:
        try:
            return self.chat_client.extract_memories(message, response)
        except Exception:
            return {"facts": [], "preferences": []}

    def ask(self, prompt: str, context: list[dict[str, Any]]) -> AIResponse:
        intent = self.classify(prompt)
        client = self.codex_client if self.TECHNICAL_PATTERN.search(prompt) else self.chat_client
        if intent == Intent.SCREEN_AWARENESS.value:
            if not self.agent_core:
                return normalize_response({"text": "屏幕感知路由尚未连接。", "emotion": "thinking"}, "tool+llm")
            return self.agent_core.execute_screen_awareness(prompt, context, client)
        if intent in (Intent.DIRECT_TOOL.value, Intent.DECISION_TASK.value):
            if not self.agent_core:
                return normalize_response({"text": "不确定，需要查询。"}, "tool+llm")
            return self.agent_core.execute_task(prompt, context, client, intent=intent)
        if intent == "search":
            data = self.network_plugin.handle(prompt)
            if not data.get("ok"):
                return normalize_response({"text": "不确定，需要查询。", "emotion": "sad"}, "tool+llm")
            return normalize_response(client.ask(inject_capability_context(f"仅根据以下搜索数据回答，不得猜测：{data}"), context), "tool+llm")
        # Ordinary chat is already a synthesizer-only path and has no factual tool claims.
        return normalize_response(client.ask(inject_capability_context(prompt), context), "codex" if client is self.codex_client else "chat")

    def ask_stream(self, prompt: str, context: list[dict[str, Any]], on_delta: Callable[[str], None]) -> AIResponse:
        intent = self.classify(prompt)
        client = self.codex_client if self.TECHNICAL_PATTERN.search(prompt) else self.chat_client
        if intent == Intent.SCREEN_AWARENESS.value:
            if not self.agent_core:
                result = normalize_response({"text": "屏幕感知路由尚未连接。", "emotion": "thinking"}, "tool+llm")
                on_delta(result["text"])
                return result
            return self.agent_core.execute_screen_awareness(prompt, context, client, on_delta)
        if intent in (Intent.DIRECT_TOOL.value, Intent.DECISION_TASK.value):
            if not self.agent_core:
                result = normalize_response({"text": "不确定，需要查询。"}, "tool+llm")
                on_delta(result["text"])
                return result
            return self.agent_core.execute_task(prompt, context, client, on_delta, intent)
        if intent == "search":
            data = self.network_plugin.handle(prompt)
            if not data.get("ok"):
                result = normalize_response({"text": "不确定，需要查询。", "emotion": "sad"}, "tool+llm")
                on_delta(result["text"])
                return result
            return normalize_response(client.ask_stream(inject_capability_context(f"仅根据以下搜索数据回答，不得猜测：{data}"), context, on_delta),
                                      "tool+llm")
        return normalize_response(client.ask_stream(inject_capability_context(prompt), context, on_delta),
                                  "codex" if client is self.codex_client else "chat")
