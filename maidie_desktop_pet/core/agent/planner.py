from __future__ import annotations

import re
from typing import Any


class Planner:
    """Creates and validates data-gathering plans; it never answers users."""

    ALLOWED_TOOLS = {"time", "weather", "search", "memory", "llm"}
    DECISION_PATTERN = re.compile(r"适不适合|是否适合|适合.*吗|能不能|是否应该|建议|去不去|要不要|该不该|推荐", re.I)

    def __init__(self, planning_client: Any) -> None:
        self.planning_client = planning_client

    def plan(self, message: str, memory_context: str, decision: bool | None = None) -> dict[str, Any]:
        is_decision = bool(self.DECISION_PATTERN.search(message)) if decision is None else decision
        try:
            candidate = self.planning_client.plan_task(message, memory_context)
            validated = self._validate(candidate, message, is_decision)
            if validated:
                return validated
        except Exception:
            pass
        return self._fallback(message, is_decision)

    def _validate(self, candidate: Any, message: str, decision: bool) -> dict[str, Any] | None:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("steps"), list):
            return None
        steps = []
        for item in candidate["steps"][:8]:
            if not isinstance(item, dict) or item.get("tool") not in self.ALLOWED_TOOLS:
                continue
            steps.append({"tool": str(item["tool"]), "action": str(item.get("action") or "执行步骤"),
                          "params": item.get("params", {}) if isinstance(item.get("params", {}), dict) else {}})
        steps = self._enforce_factual_dependencies(message, steps)
        if decision and len(steps) < 2:
            return None
        if not steps or steps[-1]["tool"] != "llm":
            steps.append(self._llm_step())
        return {"goal": str(candidate.get("goal") or message), "steps": steps}

    def _fallback(self, message: str, decision: bool) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        if re.search(r"天气|气温|温度|下雨|跑步|出门|\bweather\b", message, re.I):
            steps.append({"tool": "weather", "action": "查询客观天气数据", "params": {"query": message}})
        if re.search(r"几点|时间|日期|星期|\b(time|date|now)\b", message, re.I):
            steps.append({"tool": "time", "action": "查询客观时间数据", "params": {"query": message}})
        if re.search(r"搜索|查询|最新|资料|新闻|\b(search|latest)\b", message, re.I):
            steps.append({"tool": "search", "action": "查询外部资料", "params": {"query": message}})
        if decision and not steps:
            steps.append({"tool": "memory", "action": "读取与决策有关的用户偏好", "params": {}})
        steps.append(self._llm_step())
        return {"goal": message, "steps": steps}

    def _enforce_factual_dependencies(self, message: str, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tools = {step["tool"] for step in steps}
        prefix = []
        if re.search(r"天气|气温|温度|下雨|跑步|出门|\bweather\b", message, re.I) and "weather" not in tools:
            prefix.append({"tool": "weather", "action": "查询客观天气数据", "params": {"query": message}})
        if re.search(r"几点|时间|日期|星期|\b(time|date|now)\b", message, re.I) and "time" not in tools:
            prefix.append({"tool": "time", "action": "查询客观时间数据", "params": {"query": message}})
        return prefix + steps

    @staticmethod
    def _llm_step() -> dict[str, Any]:
        return {"tool": "llm", "action": "仅基于已取得的数据生成最终表达", "params": {}}
