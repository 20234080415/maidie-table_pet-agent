"""执行 BrainPlanner 生成的结构化步骤。

该模块位于 Planner 与 ``ToolRegistry`` 之间：它不生成用户文案，而是把不可信的
计划参数收敛为受支持的 Tool 调用，并将结果统一成供 Synthesizer 消费的数据。
"""

from __future__ import annotations

from time import monotonic
from typing import Any, Callable

from core.performance import mark
from core.tools.file_permissions import FILE_OPERATIONS


class BrainExecutor:
    """Executes planner steps and returns structured tool data only."""

    ALLOWED_TOOLS = {
        "weather", "time", "search", "screen", "memory", "system", "codex", "opencode",
        "coding_agent",
    }
    FILE_CONTINUATION_GOALS = {
        "summary", "analysis", "explain", "extract", "review", "search_related",
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
            if tool_name == "system" and isinstance(raw, dict):
                raw = self._observe_system_result(params, raw)
                safe_result["raw"] = raw
            raw_ok = raw.get("ok") if isinstance(raw, dict) else None
            execution = {
                "index": index,
                "tool": tool_name,
                "ok": bool(raw_ok) if isinstance(raw_ok, bool) else (
                    isinstance(raw, dict) and not bool(raw.get("error"))
                ),
                "data": safe_result,
            }
            continuation = self._file_continuation(tool_name, params, raw, execution["ok"])
            if continuation is not None:
                execution["continuation"] = continuation
            executions.append(execution)
        return executions

    @staticmethod
    def _observe_system_result(params: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
        observed = dict(raw)
        operation = str(
            observed.get("operation") or params.get("operation") or params.get("action") or ""
        )
        succeeded = observed.get("ok") is True or (
            "ok" not in observed and not bool(observed.get("error"))
        )
        observed.setdefault("ok", succeeded)
        observed.setdefault("operation", operation)
        if operation in {"read_file", "read_text_file"}:
            observed.setdefault("path", str(params.get("source") or ""))
        if succeeded:
            observed.setdefault("data", observed.get("result", {}))
            try:
                result_count = int(observed.get("result_count") or 0)
            except (TypeError, ValueError):
                result_count = len(observed.get("items") or [])
            observations = {
                "read_file": "file_loaded", "read_text_file": "file_loaded",
                "search_files": "files_found" if result_count else "no_matches",
                "list_directory": "directory_loaded",
            }
            observed.setdefault("observation", observations.get(operation, "operation_completed"))
            observed.setdefault("recoverable", False)
            observed.setdefault("suggestions", [])
            return observed

        code = str(observed.get("error_code") or "").strip().lower()
        security_codes = {
            "protected_path", "path_escape", "reparse_point", "device_path", "unc_path",
            "ntfs_ads", "drive_root", "workspace_root_forbidden", "user_cancelled",
            "authorization_mismatch", "authorization_expired",
        }
        not_found_codes = {
            "path_not_found", "source_not_file", "path_not_resolved", "file_not_found",
        }
        parameter_codes = {
            "path_required", "source_required", "destination_required", "paths_required",
            "invalid_path", "unsupported_operation",
        }
        type_codes = {"binary_file", "invalid_docx", "invalid_pdf", "unsupported_file_type"}
        if code in not_found_codes:
            observation, recoverable = "file_not_found", True
            suggestions = ["search_similar_file", "list_directory"]
        elif code in parameter_codes:
            observation, recoverable = "invalid_parameters", True
            suggestions = ["correct_parameters"]
        elif code in type_codes:
            observation, recoverable = "unsupported_file", True
            suggestions = ["search_similar_file"]
        elif code == "permission_denied":
            observation, recoverable = "permission_required", True
            suggestions = ["request_permission"]
        else:
            observation, recoverable = (
                "security_blocked" if code in security_codes else "operation_failed",
                False,
            )
            suggestions = []
        observed.setdefault("observation", observation)
        observed.setdefault("recoverable", recoverable)
        observed.setdefault("suggestions", suggestions)
        observed.setdefault("data", None)
        return observed

    @classmethod
    def _file_continuation(cls, tool_name: str, params: dict[str, Any],
                           raw: Any, succeeded: bool) -> dict[str, Any] | None:
        operation = str(params.get("operation") or params.get("action") or "")
        goal = str(params.get("goal") or "none").strip().lower()
        if (tool_name != "system" or operation not in {"read_file", "read_text_file"}
                or goal not in cls.FILE_CONTINUATION_GOALS or not succeeded
                or not isinstance(raw, dict) or raw.get("ok") is False):
            return None
        result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
        return {
            "type": "file_content",
            "content": str(raw.get("content") or result.get("content") or ""),
            "file_type": str(raw.get("file_type") or result.get("file_type") or "text"),
            "next_action": goal,
            "path": str(raw.get("path") or raw.get("resolved_path")
                        or params.get("source") or ""),
        }

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
        forbidden = {
            "confirmed", "risk", "resolved", "resolved_path", "resolved_source",
            "resolved_destination", "fingerprint", "authorization", "plan_id",
        }
        safe_params = {key: value for key, value in params.items() if key not in forbidden}
        try:
            if name == "system" and hasattr(tool, "execute"):
                operation = str(safe_params.get("operation") or safe_params.get("action") or "")
                if operation:
                    recovery_confirmation = bool(
                        safe_params.pop("recovery_requires_confirmation", False)
                    )
                    recovery_original = str(safe_params.pop("recovery_original_path", "") or "")
                    if recovery_confirmation and operation in {"read_file", "read_text_file"}:
                        callback = getattr(tool, "confirmation_callback", None)
                        approved = bool(callback and callback("read_file_recovery", {
                            "recovery_plan": {
                                "operation": operation,
                                "path": str(safe_params.get("source") or ""),
                                "original_path": recovery_original,
                                "risk": "medium",
                                "requires_confirmation": True,
                                "impact_scope": "single_file",
                            },
                        }))
                        if not approved:
                            return {"type": "system", "source": "local", "raw": {
                                "ok": False, "operation": operation,
                                "path": str(safe_params.get("source") or ""),
                                "error": "user confirmation required",
                                "error_code": "user_cancelled",
                                "message": "用户没有确认读取恢复候选文件",
                                "data": None, "result": None,
                            }}
                    if operation in FILE_OPERATIONS:
                        safe_params = {
                            key: value for key, value in safe_params.items()
                            if key in {
                                "operation", "source", "destination", "content",
                                "pattern", "limit", "encoding", "old_text", "new_text",
                            }
                        }
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
