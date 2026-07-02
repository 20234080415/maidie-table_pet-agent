from __future__ import annotations

import json
from typing import Any

from core.brain.intent_classifier import IntentClassifier


class LLMIntentRouter:
    """LLM-first intent gate with regex fallback only for failures."""

    INTENTS = {"chat", "task", "screen", "code_task", "system_task"}
    PROMPT = """You are the intent router of a desktop AI agent (Maidie).

You must classify user input into one of:

- chat
- task
- screen
- code_task
- system_task

Return ONLY JSON:

{
  "intent": "...",
  "confidence": 0.0-1.0,
  "reason": "short explanation"
}

Rules:
- Prefer task when tools are needed
- Prefer screen when user refers to desktop state
- Prefer code_task for coding/debug requests
- Technical documentation, API meaning, and programming knowledge questions are code_task
- A casual statement of interest (for example "I am interested in CMake") is chat unless it asks a question or requests work
- Default to chat for emotional conversation and casual statements
"""

    def __init__(self, client: Any, fallback: IntentClassifier | None = None) -> None:
        self.client = client
        self.fallback = fallback or IntentClassifier()
        self.last_route: dict[str, Any] | None = None

    def classify(self, user_input: str, context: list[dict[str, Any]] | None = None) -> str:
        route = self.route(user_input, context)
        return str(route["intent"])

    def route(self, user_input: str, context: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        try:
            route = self._route_with_llm(user_input, context or [])
            self.last_route = {**route, "source": "llm"}
            return self.last_route
        except Exception as exc:
            intent = self.fallback.classify(user_input)
            self.last_route = {
                "intent": intent,
                "confidence": 0.0,
                "reason": f"LLM router failed; fallback used: {exc}",
                "source": "fallback",
            }
            return self.last_route

    def _route_with_llm(self, user_input: str, context: list[dict[str, Any]]) -> dict[str, Any]:
        if hasattr(self.client, "route_intent"):
            raw = self.client.route_intent(self._prompt(user_input), context)
        else:
            raw = self.client.ask(self._prompt(user_input), context)
        result = self._parse(raw)
        intent = str(result.get("intent", "")).strip()
        if intent not in self.INTENTS:
            raise ValueError(f"invalid intent: {intent!r}")
        return {
            "intent": intent,
            "confidence": self._confidence(result.get("confidence")),
            "reason": str(result.get("reason") or ""),
        }

    @classmethod
    def _prompt(cls, user_input: str) -> str:
        return f"{cls.PROMPT}\nUser input:\n{user_input}"

    @classmethod
    def _parse(cls, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict) and "intent" in raw:
            return raw
        if isinstance(raw, dict):
            text = str(raw.get("text") or "").strip()
        else:
            text = str(raw).strip()
        if text.startswith("```json") and text.endswith("```"):
            text = text[7:-3].strip()
        elif text.startswith("```") and text.endswith("```"):
            text = text[3:-3].strip()
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("LLM router returned non-object JSON")
        return parsed

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
