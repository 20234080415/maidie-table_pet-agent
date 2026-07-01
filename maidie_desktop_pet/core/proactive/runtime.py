from __future__ import annotations

from typing import Any

from core.proactive.engine import ProactiveDecision


class ProactiveRuntime:
    """Coordinates Awareness -> Scheduler/Proactive -> Tools; UI/LLM stay in PetController."""

    def __init__(self, awareness: Any, engine: Any, scheduler: Any, tool_registry: Any, memory: Any) -> None:
        self.awareness, self.engine, self.scheduler = awareness, engine, scheduler
        self.tool_registry, self.memory = tool_registry, memory

    def tick(self) -> tuple[dict[str, Any], ProactiveDecision | None]:
        context = self.awareness.snapshot()
        if self._needs_weather():
            tool = self.tool_registry.get("weather")
            if tool:
                result = tool.run("今天天气")
                if not result.get("raw", {}).get("error"):
                    context["weather"] = result.get("raw", {})
        due = self.scheduler.tick(context)
        if due:
            task = due[0]
            tools = ("weather",) if isinstance(task.trigger, dict) and "weather" in task.trigger else ()
            prompt = task.action
            if tools:
                prompt = f"请先查询当前天气数据，再自然表达这个提醒：{task.action}"
            return context, ProactiveDecision("reminder", prompt, "happy", tools)
        return context, self.engine.decide(context, self.memory)

    def _needs_weather(self) -> bool:
        return any(task.enabled and task.type == "condition" and isinstance(task.trigger, dict)
                   and "weather" in task.trigger for task in self.scheduler.tasks)
