"""Deprecated compatibility layer; production execution uses :mod:`core.brain`.

Do not add new features here. This module remains only for legacy callers and
compatibility tests.
"""

from __future__ import annotations

from typing import Any


class ToolExecutor:
    """Executes data steps. No step may produce an answer to the user."""

    def __init__(self, tool_registry: Any, network_plugin: Any, memory: Any) -> None:
        self.tool_registry, self.network_plugin, self.memory = tool_registry, network_plugin, memory

    def execute(self, plan: dict[str, Any], message: str) -> list[dict[str, Any]]:
        context = []
        for index, step in enumerate(plan.get("steps", [])):
            tool_name = str(step.get("tool", ""))
            try:
                result = self._run_step(tool_name, step, message)
                result.pop("text", None)
                ok = not bool(result.get("raw", {}).get("error"))
            except Exception as exc:
                result = {"type": tool_name, "raw": {"error": str(exc)}, "source": "local"}
                ok = False
            context.append({"index": index, "step": step, "ok": ok, "result": result})
        return context

    def _run_step(self, tool_name: str, step: dict[str, Any], message: str) -> dict[str, Any]:
        raw_params = step.get("params", {}) if isinstance(step.get("params", {}), dict) else {}
        # Plans are untrusted: confirmation can only come from the trusted broker path.
        params = {key: value for key, value in raw_params.items() if key != "confirmed"}
        query = str(params.get("query") or message)
        if tool_name in ("time", "weather"):
            tool = self.tool_registry.get(tool_name)
            if tool is None:
                raise LookupError(f"tool not registered: {tool_name}")
            return tool.run(query)
        if tool_name == "system":
            tool = self.tool_registry.get("system")
            if tool is None:
                raise LookupError("tool not registered: system")
            operation = str(params.get("operation") or step.get("action") or "")
            return tool.execute(operation, params)
        if tool_name == "search":
            result = self.network_plugin.handle(query)
            return {"type": "search", "raw": result, "source": "api"}
        if tool_name == "memory":
            return {"type": "memory", "raw": {"memories": self.memory.load_memories(20)}, "source": "local"}
        if tool_name == "llm":
            return {"type": "llm", "raw": {"deferred": True}, "source": "local"}
        raise ValueError(f"unsupported tool: {tool_name}")
