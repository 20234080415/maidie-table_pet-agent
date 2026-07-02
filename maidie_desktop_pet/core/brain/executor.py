from __future__ import annotations

from time import monotonic
from typing import Any

from core.performance import mark


class BrainExecutor:
    """Executes planner steps and returns structured tool data only."""

    ALLOWED_TOOLS = {
        "weather", "time", "search", "screen", "memory", "system", "codex", "opencode",
    }

    def __init__(self, tool_registry: Any) -> None:
        self.tool_registry = tool_registry

    def execute(self, plan: dict[str, Any], user_input: str) -> list[dict[str, Any]]:
        executions = []
        for index, step in enumerate(plan.get("steps", [])):
            tool_name = str(step.get("tool", "")) if isinstance(step, dict) else ""
            try:
                params = step.get("params", {}) if isinstance(step.get("params"), dict) else {}
                if tool_name not in self.ALLOWED_TOOLS:
                    result = self._error(tool_name, "tool blocked by executor")
                else:
                    started = monotonic()
                    try:
                        result = self._execute_tool(tool_name, user_input, params)
                    finally:
                        mark(tool_name=tool_name,
                             tool_duration_ms=round((monotonic() - started) * 1000, 3))
                if not isinstance(result, dict):
                    raise TypeError("tool returned a non-structured result")
                safe_result = dict(result)
            except Exception as exc:
                safe_result = self._error(tool_name, str(exc))
            safe_result.pop("text", None)
            raw = safe_result.get("raw", {})
            executions.append({
                "index": index,
                "tool": tool_name,
                "ok": isinstance(raw, dict) and not bool(raw.get("error")),
                "data": safe_result,
            })
        return executions

    def _execute_tool(self, name: str, user_input: str,
                      params: dict[str, Any]) -> dict[str, Any]:
        tool = self.tool_registry.get(name)
        if tool is None:
            return self._error(name, f"{name} unavailable")

        # Planner/LLM parameters are data, never trusted authorization.
        safe_params = dict(params)
        safe_params.pop("confirmed", None)
        try:
            if name == "system" and hasattr(tool, "execute"):
                operation = str(safe_params.get("operation") or safe_params.get("action") or "")
                if operation:
                    return tool.execute(operation, safe_params)
            if name == "memory":
                return tool.run(
                    user_input,
                    kind=str(safe_params.get("kind", "long_term")),
                    limit=int(safe_params.get("limit", 20)),
                )
            if name == "search":
                return tool.run(
                    str(safe_params.get("query") or ""),
                    raw_user_text=user_input,
                    query_source=str(safe_params.get("query_source") or "explicit_user_text"),
                )
            if name == "screen":
                return tool.run(
                    str(safe_params.get("query") or user_input),
                    scope=str(safe_params.get("scope") or "active_window"),
                    reuse_session=bool(safe_params.get("reuse_session", False)),
                    force_refresh=bool(safe_params.get("force_refresh", False)),
                    selected_rect=(tuple(safe_params["selected_rect"])
                                   if isinstance(safe_params.get("selected_rect"), (list, tuple))
                                   and len(safe_params["selected_rect"]) == 4 else None),
                )
            return tool.run(str(safe_params.get("query") or user_input))
        except Exception as exc:
            return self._error(name, str(exc))

    @staticmethod
    def _error(tool_name: str, message: str) -> dict[str, Any]:
        return {"type": tool_name, "raw": {"error": message}, "source": "local"}
