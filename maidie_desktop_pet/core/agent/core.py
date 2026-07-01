from __future__ import annotations

import json
from typing import Any, Callable

from ai.client import AIResponse, normalize_response
from ai.prompt import inject_capability_context
from core.agent.intent import Intent


class AgentCore:
    """Planner -> data tools -> Synthesizer pipeline."""

    def __init__(self, detector: Any, planner: Any, executor: Any, memory: Any,
                 awareness_provider: Any | None = None) -> None:
        self.detector, self.planner, self.executor, self.memory = detector, planner, executor, memory
        self._memory_snapshot: dict[str, Any] = {}
        self.awareness_provider = awareness_provider

    def detect_intent(self, message: str) -> str:
        self._memory_snapshot = self._load_memory()
        return self.detector.detect(message)

    def plan_task(self, message: str, decision: bool | None = None) -> dict[str, Any]:
        snapshot = self._memory_snapshot or self._load_memory()
        return self.planner.plan(message, self._planner_context(snapshot), decision=decision)

    def execute_task(self, message: str, context: list[dict[str, Any]], client: Any,
                     on_delta: Callable[[str], None] | None = None,
                     intent: str | None = None) -> AIResponse:
        intent = intent or self.detect_intent(message)
        snapshot = self._memory_snapshot or self._load_memory()
        memory_context = self._planner_context(snapshot)
        awareness = self._awareness_snapshot()
        planning_context = memory_context + ("\n桌面上下文（仅供当前任务）：" + json.dumps(awareness, ensure_ascii=False, default=str) if awareness else "")
        plan = self.planner.plan(message, planning_context, decision=intent == Intent.DECISION_TASK.value)
        executions = self.executor.execute(plan, message)
        required = [item for item in executions if item["step"].get("tool") not in ("llm", "memory")]
        if required and not all(item["ok"] for item in required):
            return self._uncertain(on_delta)
        if self._requires(message, "weather") and not self._has_data(executions, "weather"):
            return self._uncertain(on_delta)
        if self._requires(message, "time") and not self._has_data(executions, "time"):
            return self._uncertain(on_delta)

        synthesis_prompt = inject_capability_context(
            "你是唯一允许向用户输出最终回答的 Synthesizer。\n"
            "只能使用下方工具数据和记忆；不得猜测、补全或编造天气、时间及搜索事实。"
            "数据不足时只能回答‘不确定，需要查询’。不要提及内部计划。\n"
            f"用户问题：{message}\n计划：{json.dumps(plan, ensure_ascii=False)}\n"
            f"工具数据：{json.dumps(executions, ensure_ascii=False, default=str)}\n"
            f"相关记忆：{memory_context or '无'}\n"
            f"桌面与应用上下文：{json.dumps(awareness, ensure_ascii=False, default=str)}\n"
            "请输出包含 text、emotion、action、state 的 JSON。"
        )
        try:
            response = client.ask_stream(synthesis_prompt, context, on_delta) if on_delta else client.ask(synthesis_prompt, context)
            result = normalize_response(response, "tool+llm")
            result.update({"action": "talk", "state": "talking", "source": "tool+llm"})
            return result
        except Exception:
            return self._uncertain(on_delta)

    def execute_screen_awareness(self, message: str, context: list[dict[str, Any]], client: Any,
                                 on_delta: Callable[[str], None] | None = None) -> AIResponse:
        """Collect desktop reality first, then let the LLM explain only that data."""
        try:
            awareness = self.awareness_provider.screen_awareness_snapshot()
        except Exception as exc:
            awareness = {
                "screen_text": "", "app": "unknown", "window": "", "context": "unknown",
                "tool_status": {"screen_ocr": f"error: {exc}", "app_tracker": "error",
                                "window_tracker": "error"},
            }
        synthesis_prompt = inject_capability_context(
            "你是 SCREEN_AWARENESS 模式的解释器。三项工具已经由 Router 调用。"
            "只能依据工具结果回答当前屏幕、应用和用户活动；不得猜测，也不得回答‘我看不到屏幕’。"
            "若工具失败，应明确说明具体工具暂时未取得数据，并建议检查 OCR 配置。\n"
            f"用户问题：{message}\nAwareness 工具结果：{json.dumps(awareness, ensure_ascii=False, default=str)}\n"
            "请直接解释结果，并输出包含 text、emotion、action、state 的 JSON。"
        )
        try:
            response = (client.ask_stream(synthesis_prompt, context, on_delta)
                        if on_delta else client.ask(synthesis_prompt, context))
            result = normalize_response(response, "tool+llm")
            result.update({"action": "talk", "state": "talking", "source": "tool+llm"})
            return result
        except Exception:
            text = "屏幕感知工具本次没有取得可用结果，请检查 OCR 是否安装并重试。"
            result = normalize_response({"text": text, "emotion": "thinking"}, "tool+llm")
            if on_delta:
                on_delta(text)
            return result

    @staticmethod
    def _requires(message: str, kind: str) -> bool:
        words = {"weather": ("天气", "气温", "温度", "下雨", "跑步", "出门", "weather"),
                 "time": ("几点", "时间", "日期", "星期", "time", "date")}
        lowered = message.lower()
        return any(word in lowered for word in words[kind])

    @staticmethod
    def _has_data(executions: list[dict[str, Any]], kind: str) -> bool:
        return any(item["ok"] and item["result"].get("type") == kind and item["result"].get("raw")
                   for item in executions)

    @staticmethod
    def _uncertain(on_delta: Callable[[str], None] | None) -> AIResponse:
        result = normalize_response({"text": "不确定，需要查询。", "emotion": "sad",
                                     "action": "talk", "state": "talking"}, "tool+llm")
        if on_delta:
            on_delta(result["text"])
        return result

    def _load_memory(self) -> dict[str, Any]:
        try:
            return {"background": self.memory.prompt_context(), "memories": self.memory.load_memories(20),
                    "recent_chats": self.memory.get_recent()[-20:]}
        except Exception:
            return {"background": "", "memories": [], "recent_chats": []}

    def _awareness_snapshot(self) -> dict[str, Any]:
        if not self.awareness_provider:
            return {}
        try:
            return self.awareness_provider.snapshot()
        except Exception:
            return {}

    @staticmethod
    def _planner_context(snapshot: dict[str, Any]) -> str:
        background = str(snapshot.get("background", ""))
        recent = snapshot.get("recent_chats", [])
        return background + (("\n最近对话（仅供规划）：" + json.dumps(recent, ensure_ascii=False, default=str)) if recent else "")
