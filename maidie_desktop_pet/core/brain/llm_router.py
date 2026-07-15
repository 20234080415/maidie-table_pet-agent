"""把用户输入规范化为 BrainPlanner 可消费的意图元数据。

路由优先复用 Session 短期上下文和确定性 fast route，再请求 LLM；所有来源最终经过
同一 schema 归一化，失败时退回 ``IntentClassifier``，且不在此执行 Tool。
"""

from __future__ import annotations

import json
from typing import Any

from core.brain.fast_route import fast_route
from core.brain.intent_classifier import IntentClassifier
from core.prompts.router import ROUTER_PROMPT
from core.session.task_context import ShortTermTaskContext


class LLMIntentRouter:
    """LLM-first intent gate with regex fallback only for failures."""

    INTENTS = {"chat", "task", "vision", "clarification", "code_task", "system_task"}
    ENTITY_KEYS = ("target_time_text", "time_text", "event", "location", "query")
    PROMPT = ROUTER_PROMPT

    def __init__(self, client: Any, fallback: IntentClassifier | None = None) -> None:
        self.client = client
        self.fallback = fallback or IntentClassifier()
        self.last_route: dict[str, Any] | None = None
        self.task_context = ShortTermTaskContext()

    def classify(self, user_input: str, context: list[dict[str, Any]] | None = None) -> str:
        route = self.route(user_input, context)
        # Keep the legacy classifier API stable while route() exposes the
        # more precise vision intent and metadata to new callers.
        return "screen" if route["intent"] == "vision" else str(route["intent"])

    def clear_context(self) -> None:
        self.last_route = None
        self.task_context = ShortTermTaskContext()

    def route(self, user_input: str, context: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """生成包含 intent、task_type、entities 与权限提示的标准 route。

        ``context`` 只恢复当前 Session 的短期事实；结果保存到 ``last_route``，供
        ``BrainRouter`` 在兼容 classify 接口之后继续构造 Plan。
        """
        history_context = ShortTermTaskContext.from_messages(context or [])
        # 先解析依赖上一轮事件时间的追问，避免为确定性上下文再次请求 LLM。
        self.task_context.event_times.update(history_context.event_times)
        contextual = self.task_context.resolve(user_input)
        self.task_context.observe(user_input)
        if contextual:
            self.last_route = self._normalize({**contextual, "confidence": 1.0, "reason": "event time from short-term context",
                               "source": "session_context", "route_source": "session_context",
                               "need_screen": False, "need_vision": False,
                               "permission_required": False})
            return self.last_route
        deterministic = fast_route(user_input)
        if deterministic:
            self.last_route = self._normalize(deterministic)
            return self.last_route
        try:
            route = self._route_with_llm(user_input, context or [])
            self.last_route = self._normalize({**route, "source": "llm", "route_source": "llm"})
            return self.last_route
        except Exception as exc:
            intent = self.fallback.classify(user_input)
            self.last_route = self._normalize({
                "intent": intent,
                "confidence": 0.0,
                "reason": f"LLM router failed; fallback used: {exc}",
                "source": "fallback",
                "route_source": "fallback",
            })
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
        need_vision = intent == "vision"
        return {
            "intent": intent,
            "confidence": self._confidence(result.get("confidence")),
            "reason": str(result.get("reason") or ""),
            "need_screen": need_vision,
            "need_vision": need_vision,
            "permission_required": need_vision,
            "task_type": str(result.get("task_type") or ("screen_understanding" if need_vision else "none")),
            "needs_tools": bool(result.get("needs_tools", intent in {"task", "vision"})),
            "entities": dict(result.get("entities") or {}),
        }

    @classmethod
    def _normalize(cls, route: dict[str, Any]) -> dict[str, Any]:
        result = dict(route)
        intent = str(result.get("intent") or "chat")
        task_type = str(result.get("task_type") or "none")
        entities = dict(result.get("entities") or {})
        result["intent"] = intent
        result["task_type"] = task_type
        result["entities"] = {key: entities.get(key) for key in cls.ENTITY_KEYS}
        result["needs_tools"] = bool(result.get("needs_tools", intent in {"task", "vision"}))
        result["confidence"] = cls._confidence(result.get("confidence"))
        result["reason"] = str(result.get("reason") or "")
        return result

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
