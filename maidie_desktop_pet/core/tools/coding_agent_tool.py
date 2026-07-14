from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from core.tools.base import Tool, ToolResult
from core.tools.coding_agent_process import CodingAgentProcessRunner


class CodingAgentTool(Tool):
    """Read-only adapter for a local OpenCode or Codex CLI."""

    name = "coding_agent"
    OPERATIONS = {
        "analyze_project", "explain_module", "propose_fix", "propose_patch", "test_plan",
    }

    def __init__(self, workspace: dict[str, Any] | None = None,
                 options: dict[str, Any] | None = None) -> None:
        self.workspace = dict(workspace or {})
        self.options = dict(options or {})
        self.runner = CodingAgentProcessRunner(max_lines=200)
        self.callbacks: dict[str, Any] = {}

    def configure(self, workspace: dict[str, Any] | None = None,
                  options: dict[str, Any] | None = None) -> None:
        self.workspace = dict(workspace or {})
        self.options = dict(options or {})

    def set_progress_callbacks(self, **callbacks: Any) -> None:
        self.callbacks = dict(callbacks)

    def cancel(self) -> None:
        self.runner.cancel()

    shutdown = cancel

    @staticmethod
    def validate_configuration(workspace_root: str, provider: str, command: str,
                               dry_run: bool) -> dict[str, str | bool]:
        """Validate UI configuration without starting the coding CLI."""
        try:
            root_text = str(workspace_root or "").strip()
            if not root_text:
                return {"ok": False, "code": "workspace_not_configured",
                        "message": "workspace 未配置"}
            root = Path(root_text).expanduser().resolve()
            if not root.is_dir():
                return {"ok": False, "code": "workspace_invalid",
                        "message": "workspace 不存在或不是目录"}
            normalized_provider = str(provider or "").strip().lower()
            if normalized_provider not in {"opencode", "codex"}:
                return {"ok": False, "code": "provider_unsupported",
                        "message": "provider 不支持"}
            if not bool(dry_run):
                return {"ok": False, "code": "configuration_invalid",
                        "message": "配置异常：dry_run 必须开启"}
            if not shutil.which(str(command or "").strip()):
                return {"ok": False, "code": "command_unavailable",
                        "message": "command 不可用"}
            return {"ok": True, "code": "available", "message": "可用"}
        except (OSError, RuntimeError, ValueError, TypeError):
            return {"ok": False, "code": "configuration_invalid", "message": "配置异常"}

    def match(self, query: str) -> bool:
        return False  # Planner selection is explicit; registry auto-match must stay conservative.

    def run(self, query: str, operation: str = "analyze_project",
            target_path: str = "",
            on_event: Callable[[dict[str, Any]], None] | None = None) -> ToolResult:
        source = f"local_{str(self.options.get('provider') or 'opencode').lower()}"
        base = self._raw(operation)
        if not bool(self.options.get("enabled", False)):
            return self._error(base, source, "disabled", "Coding agent 未启用")
        if not bool(self.options.get("dry_run", True)):
            return self._error(base, source, "dry_run_required", "第一版仅允许 dry-run / analysis 模式")
        if operation not in self.OPERATIONS:
            return self._error(base, source, "operation_blocked", "不支持的 coding agent 操作")

        root_text = str(self.workspace.get("root") or "").strip()
        if not root_text:
            return self._error(base, source, "workspace_not_configured", "workspace 未配置")
        root = Path(root_text).expanduser().resolve()
        base["workspace_root"] = str(root)
        if not root.is_dir():
            return self._error(base, source, "workspace_unavailable", "workspace 路径不存在或不可用")
        if target_path:
            target = self._resolve_target(root, target_path)
            if target is None:
                return self._error(base, source, "path_outside_workspace", "目标路径不在 workspace.root 内")

        provider = str(self.options.get("provider") or "opencode").lower()
        command = str(self.options.get("command") or provider).strip()
        if provider not in {"opencode", "codex"}:
            return self._error(base, source, "provider_unsupported", "仅支持 OpenCode 或 Codex")
        executable = shutil.which(command)
        if not executable:
            return self._error(base, source, "cli_not_found", "未安装 OpenCode/Codex，或未配置可用路径")

        timeout = max(1, min(600, int(self.options.get("timeout_seconds", 120))))
        prompt = self._prompt(query, operation, target_path)
        args, input_text, env = self._command(provider, executable, prompt)
        def forward(name: str, payload: dict[str, Any]) -> None:
            callback = self.callbacks.get(name)
            if callback is not None:
                callback(payload)
            if on_event is None:
                return
            if name == "on_output_line":
                on_event({
                    "type": "token", "mode": "TASK_STREAM",
                    "content": str(payload.get("line") or ""),
                    "source": str(payload.get("stream") or source),
                    "tool": self.name, "phase": "output",
                })
            elif name == "on_status_change":
                on_event({
                    "type": "progress", "mode": "TASK_PROGRESS", "content": "",
                    "source": source, "tool": self.name,
                    "phase": str(payload.get("status") or "running"),
                })
            elif name == "on_finish":
                on_event({
                    "type": "complete", "mode": "TASK_STREAM", "content": "",
                    "source": source, "tool": self.name,
                    "phase": str(payload.get("status") or "failed"),
                })

        process_result = self.runner.run(
            args, str(root), input_text=input_text, timeout=timeout,
            # OpenCode can spend a long time reading files without emitting a
            # complete line. Its total timeout still applies, but line silence
            # must not be treated as a hung process.
            idle_timeout=(None if provider == "opencode" else
                          max(5, min(120, int(self.options.get("idle_timeout_seconds", 30))))),
            env=env, on_start=lambda payload: forward("on_start", payload),
            on_output_line=lambda payload: forward("on_output_line", payload),
            on_status_change=lambda payload: forward("on_status_change", payload),
            on_finish=lambda payload: forward("on_finish", payload),
        )
        base["process"] = process_result
        base["stderr"] = process_result.get("stderr_tail", "")
        status = str(process_result.get("status") or "failed")
        if status != "completed":
            messages = {
                "timeout": "Coding Agent 超时，已终止进程树",
                "idle_timeout": "Coding Agent 无输出超时，可能正在等待配置",
                "needs_setup": "OpenCode 需要配置模型 provider / API Key",
                "cancelled": "用户已取消本次 Coding Agent 任务",
                "failed": "Coding Agent CLI 执行失败",
            }
            return self._error(base, source, status, messages.get(status, "Coding Agent 执行失败"))
        self._merge_output(base, str(process_result.get("stdout_tail") or ""))
        return {"type": self.name, "raw": base, "source": source}

    @staticmethod
    def _resolve_target(root: Path, target_path: str) -> Path | None:
        candidate = Path(target_path).expanduser()
        candidate = (candidate if candidate.is_absolute() else root / candidate).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    @staticmethod
    def _command(provider: str, executable: str,
                 prompt: str) -> tuple[list[str], str | None, dict[str, str]]:
        env = os.environ.copy()
        if provider == "codex":
            return ([executable, "exec", "--sandbox", "read-only",
                     "--skip-git-repo-check", "-"], prompt, env)
        # OpenCode's own permission layer denies edits and command execution.
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps({
            "permission": {"edit": "deny", "bash": "deny", "webfetch": "deny",
                           "external_directory": "deny"}
        })
        env["NO_COLOR"] = "1"
        env["FORCE_COLOR"] = "0"
        return [executable, "run", prompt], None, env

    @staticmethod
    def _prompt(query: str, operation: str, target_path: str) -> str:
        return (
            "You are in read-only analysis mode. Never edit, create, delete, install, commit, push, "
            "or run shell commands. Inspect only the configured workspace. Return one JSON object "
            "with keys summary, findings, suggested_changes, patch_preview, tests_suggested. "
            f"Operation: {operation}. Target: {target_path or '.'}. User request: {query}"
        )

    def _raw(self, operation: str) -> dict[str, Any]:
        return {
            "operation": operation,
            "workspace_root": "",
            "summary": "",
            "findings": [],
            "suggested_changes": [],
            "patch_preview": "",
            "tests_suggested": [],
        }

    @staticmethod
    def _merge_output(raw: dict[str, Any], stdout: str) -> None:
        output = (stdout or "").strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", output, re.IGNORECASE | re.DOTALL)
        if fenced:
            output = fenced.group(1).strip()
        try:
            parsed = json.loads(output)
        except (TypeError, json.JSONDecodeError):
            raw["summary"] = output
            return
        if not isinstance(parsed, dict):
            raw["summary"] = output
            return
        raw["summary"] = str(parsed.get("summary") or "")
        raw["findings"] = parsed.get("findings") if isinstance(parsed.get("findings"), list) else []
        raw["suggested_changes"] = (parsed.get("suggested_changes")
                                    if isinstance(parsed.get("suggested_changes"), list) else [])
        raw["patch_preview"] = str(parsed.get("patch_preview") or "")
        raw["tests_suggested"] = (parsed.get("tests_suggested")
                                  if isinstance(parsed.get("tests_suggested"), list) else [])

    @staticmethod
    def _error(raw: dict[str, Any], source: str, code: str, message: str) -> ToolResult:
        raw["error_code"] = code
        raw["error"] = message
        return {"type": "coding_agent", "raw": raw, "source": source}
