from __future__ import annotations

import re
from typing import Any


class BrainPlanner:
    """Builds deterministic data plans and never produces user-facing prose."""

    DECISION = re.compile(r"适不适合|是否适合|适合.*吗|要不要|该不该|是否应该|建议|推荐|should", re.I)

    def plan(self, user_input: str, memory: Any = None) -> dict[str, Any]:
        text = str(user_input).strip()
        steps: list[dict[str, Any]] = []
        needs_weather = bool(re.search(r"天气|气温|温度|下雨|跑步|出门|weather|temperature", text, re.I))
        needs_time = bool(re.search(r"几点|时间|日期|星期|\btime\b|\bdate\b", text, re.I))
        if needs_weather:
            steps.append(self._step("weather", "读取天气事实", {"query": text}))
        if needs_time:
            steps.append(self._step("time", "读取本地时间", {"query": text}))
        if (not needs_weather and not needs_time
                and re.search(r"查资料|查一下|查询|搜索|最新|新闻|search|look up|latest", text, re.I)):
            steps.append(self._step("search", "读取检索资料", {"query": text}))
        if self.DECISION.search(text):
            steps.append(self._step("memory", "读取相关偏好", {"limit": 20}))
            if len(steps) < 2:
                steps.append(self._step("memory", "读取近期上下文", {"kind": "recent", "limit": 20}))
        if not steps:
            steps.append(self._step("memory", "读取任务上下文", {"limit": 20}))
        return {"goal": text, "steps": steps}

    @staticmethod
    def screen_plan(user_input: str) -> dict[str, Any]:
        return {"goal": str(user_input).strip(), "steps": [
            BrainPlanner._step("screen", "读取当前桌面事实", {"force": True})
        ]}

    @staticmethod
    def _step(tool: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"tool": tool, "action": action, "params": params}
