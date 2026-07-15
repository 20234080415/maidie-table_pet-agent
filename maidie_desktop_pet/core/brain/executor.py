"""执行 BrainPlanner 生成的结构化步骤。

该模块位于 Planner 与 ``ToolRegistry`` 之间：它不生成用户文案，而是把不可信的
计划参数收敛为受支持的 Tool 调用，并将结果统一成供 Synthesizer 消费的数据。
"""

from __future__ import annotations

from time import monotonic
from typing import Any, Callable

from core.performance import mark


class BrainExecutor:
    """Executes planner steps and returns structured tool data only."""

    ALLOWED_TOOLS = {
        "weather", "time", "search", "screen", "memory", "system", "codex", "opencode",
        "coding_agent",
    }

    def __init__(self, tool_registry: Any) -> None:
        self.tool_registry = tool_registry

    def execute(
        self, plan: dict[str, Any], user_input: str,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        """按顺序执行计划并返回结构化执行记录。

        ``plan`` 来自 Planner，仍需在此校验 Tool allowlist、参数和返回类型；
        ``on_event`` 仅传递进度事件。单步失败会转成错误数据而不打断整个 Agent 流程。
        """
        executions = []
        for index, step in enumerate(plan.get("steps", [])):
            tool_name = str(step.get("tool", "")) if isinstance(step, dict) else ""
            try:
                params = step.get("params", {}) if isinstance(step.get("params"), dict) else {}
                # 后续步骤可以依赖前序的结构化事实，但不能直接读取自然语言输出。
                params = self._resolve_dependent_params(tool_name, params, executions)
                if params is None:
                    continue
                if tool_name not in self.ALLOWED_TOOLS:
                    result = self._error(tool_name, "tool blocked by executor")
                else:
                    progress = self._progress_event(tool_name, params)
                    if progress is not None and on_event is not None:
                        on_event(progress)
                    started = monotonic()
                    try:
                        result = self._execute_tool(
                            tool_name, user_input, params, on_event=on_event,
                        )
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

    @staticmethod
    def _resolve_dependent_params(name: str, params: dict[str, Any],
                                  executions: list[dict[str, Any]]) -> dict[str, Any] | None:
        safe = dict(params)
        if name != "search" or safe.get("query_from") != "problem_context":
            return safe
        screen = next((item for item in reversed(executions)
                       if item.get("tool") == "screen" and item.get("ok")), None)
        raw = screen.get("data", {}).get("raw", {}) if screen else {}
        problem = raw.get("problem_context", {}) if isinstance(raw, dict) else {}
        if not isinstance(problem, dict) or not problem.get("needs_search"):
            return None
        query = str(problem.get("search_query") or "").strip()
        if not query:
            return None
        safe.pop("query_from", None)
        safe.pop("conditional", None)
        safe["query"] = query
        return safe

    def _execute_tool(
        self, name: str, user_input: str, params: dict[str, Any],
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        tool = self.tool_registry.get(name)
        if tool is None:
            return self._error(name, f"{name} unavailable")

        # Planner/LLM 参数只是数据，不能被视为用户授权；确认必须在执行边界重新建立。
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
            if name == "coding_agent":
                return tool.run(
                    user_input,
                    operation=str(safe_params.get("operation") or "analyze_project"),
                    target_path=str(safe_params.get("target_path") or ""),
                    on_event=on_event,
                )
            if name == "time" and hasattr(tool, "execute"):
                return tool.execute(
                    str(safe_params.get("action") or "now"),
                    target_time_text=str(safe_params.get("target_time_text") or ""),
                    event=str(safe_params.get("event") or ""),
                )
            return tool.run(str(safe_params.get("query") or user_input))
        except Exception as exc:
            return self._error(name, str(exc))

    @staticmethod
    def _error(tool_name: str, message: str) -> dict[str, Any]:
        return {"type": tool_name, "raw": {"error": message}, "source": "local"}

    @staticmethod
    def _progress_event(tool_name: str, params: dict[str, Any]) -> dict[str, str] | None:
        if tool_name == "search":
            content = "正在搜索..."
        elif tool_name == "system":
            operation = str(params.get("operation") or params.get("action") or "")
            content = "正在搜索文件..." if operation == "search_files" else "正在读取文件..."
        elif tool_name == "coding_agent":
            content = "正在分析项目..."
        else:
            return None
        return {
            "type": "progress",
            "mode": "TASK_PROGRESS",
            "content": content,
            "source": "tool",
            "tool": tool_name,
            "phase": "running",
        }
