from __future__ import annotations

import re
from typing import Any


class Planner:
    """Creates and validates data-gathering plans; it never answers users."""

    ALLOWED_TOOLS = {"time", "weather", "search", "system", "memory", "llm"}
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
            tool = str(item["tool"])
            params = item.get("params", {}) if isinstance(item.get("params", {}), dict) else {}
            operation = str(params.get("operation", ""))
            requires_confirmation = bool(item.get("requires_confirmation", False))
            if tool == "system" and operation not in {"read_file", "search_files", "screenshot"}:
                requires_confirmation = True
            steps.append({"tool": tool, "action": str(item.get("action") or "执行步骤"),
                          "params": params, "requires_confirmation": requires_confirmation})
        steps = self._enforce_factual_dependencies(message, steps)
        if decision and len(steps) < 2:
            return None
        if not steps or steps[-1]["tool"] != "llm":
            steps.append(self._llm_step())
        return {"goal": str(candidate.get("goal") or message), "steps": steps}

    def _fallback(self, message: str, decision: bool) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        if re.search(r"天气|气温|温度|下雨|跑步|出门|\bweather\b", message, re.I):
            steps.append({"tool": "weather", "action": "查询客观天气数据", "params": {"query": message}, "requires_confirmation": False})
        if re.search(r"几点|时间|日期|星期|\b(time|date|now)\b", message, re.I):
            steps.append({"tool": "time", "action": "查询客观时间数据", "params": {"query": message}, "requires_confirmation": False})
        if re.search(r"搜索|查询|最新|资料|新闻|\b(search|latest)\b", message, re.I):
            steps.append({"tool": "search", "action": "查询外部资料", "params": {"query": message}, "requires_confirmation": False})
        system_step = self._system_step(message)
        if system_step:
            steps.append(system_step)
        if decision and not steps:
            steps.append({"tool": "memory", "action": "读取与决策有关的用户偏好", "params": {}, "requires_confirmation": False})
        steps.append(self._llm_step())
        return {"goal": message, "steps": steps}

    def _enforce_factual_dependencies(self, message: str, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tools = {step["tool"] for step in steps}
        prefix = []
        if re.search(r"天气|气温|温度|下雨|跑步|出门|\bweather\b", message, re.I) and "weather" not in tools:
            prefix.append({"tool": "weather", "action": "查询客观天气数据", "params": {"query": message}, "requires_confirmation": False})
        if re.search(r"几点|时间|日期|星期|\b(time|date|now)\b", message, re.I) and "time" not in tools:
            prefix.append({"tool": "time", "action": "查询客观时间数据", "params": {"query": message}, "requires_confirmation": False})
        return prefix + steps

    @staticmethod
    def _llm_step() -> dict[str, Any]:
        return {"tool": "llm", "action": "仅基于已取得的数据生成最终表达", "params": {},
                "requires_confirmation": False}

    @staticmethod
    def _system_step(message: str) -> dict[str, Any] | None:
        rules = (
            ("read_file", r"读取文件|查看文件", False),
            ("search_files", r"搜索文件|查找文件", False),
            ("create_file", r"创建文件|新建文件", True),
            ("open_app", r"打开.*(?:notepad|记事本|vscode|chrome)", True),
            ("open_folder", r"打开文件夹|打开目录", True),
            ("switch_window", r"切换窗口", True),
            ("screenshot", r"截图|屏幕截图", False),
            ("copy_clipboard", r"复制.*剪贴板|写入剪贴板", True),
        )
        for operation, pattern, confirm in rules:
            if re.search(pattern, message, re.I):
                params: dict[str, Any] = {"operation": operation, "query": message}
                quoted = re.search(r"[\"“](.+?)[\"”]", message)
                if quoted:
                    params["path" if "file" in operation or operation == "open_folder" else "text"] = quoted.group(1)
                if operation == "open_app":
                    lowered = message.lower()
                    params["app"] = "vscode" if "vscode" in lowered else "chrome" if "chrome" in lowered else "notepad"
                return {"tool": "system", "action": operation, "params": params,
                        "requires_confirmation": confirm}
        return None
