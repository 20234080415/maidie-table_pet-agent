"""把受限工作区内的 Coding Agent 能力封装为结构化 Tool。

本模块验证启用状态、workspace 边界、provider/command 与操作类型，再委托
``CodingAgentProcessRunner``；原始 CLI 输出会被归一化供 Executor 和 Synthesizer 使用。
"""

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


class _OpenCodeJsonStream:
    """Turn OpenCode JSONL protocol records into short, useful UI messages."""

    def __init__(self) -> None:
        self._buffer = ""
        self._text_parts: list[str] = []
        self.protocol_errors = 0

    @property
    def final_text(self) -> str:
        return "\n".join(part for part in self._text_parts if part).strip()

    def feed(self, stream: str, chunk: str) -> list[dict[str, str]]:
        if stream != "stdout":
            content = str(chunk or "").strip()
            if not content:
                return []
            return [{"stream": "stderr", "line": self._short(content, 500)}]
        self._buffer += str(chunk or "")
        visible: list[dict[str, str]] = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            message = self._parse_line(line)
            if message:
                visible.append({"stream": "status", "line": message})
        return visible

    def finish(self) -> list[dict[str, str]]:
        if not self._buffer.strip():
            self._buffer = ""
            return []
        message = self._parse_line(self._buffer)
        self._buffer = ""
        return [{"stream": "status", "line": message}] if message else []

    def _parse_line(self, line: str) -> str:
        text = line.strip()
        if not text:
            return ""
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            self.protocol_errors += 1
            return "OpenCode 输出协议异常，原始内容已写入日志"
        if not isinstance(event, dict):
            return ""
        event_type = str(event.get("type") or "")
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        if event_type == "text":
            final_text = str(part.get("text") or "")
            if final_text:
                self._text_parts.append(final_text)
                return "OpenCode 已生成结构化结果"
            return ""
        if event_type == "tool_use":
            return self._tool_message(part)
        if event_type in {"error", "session_error"}:
            detail = str(event.get("error") or part.get("error") or "未知错误")
            return "OpenCode 错误：" + self._short(detail, 300)
        return ""

    @classmethod
    def _tool_message(cls, part: dict[str, Any]) -> str:
        tool = str(part.get("tool") or "工具").lower()
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        inputs = state.get("input") if isinstance(state.get("input"), dict) else {}
        if tool == "read":
            target = Path(str(inputs.get("filePath") or "文件")).name or "文件"
            return f"OpenCode 正在读取 {cls._short(target, 120)}"
        if tool in {"grep", "search"}:
            pattern = str(inputs.get("pattern") or inputs.get("query") or "代码")
            return f"OpenCode 正在搜索 {cls._short(pattern, 120)}"
        if tool in {"glob", "find"}:
            pattern = str(inputs.get("pattern") or "文件")
            return f"OpenCode 正在查找 {cls._short(pattern, 120)}"
        return f"OpenCode 正在使用 {cls._short(tool, 80)}"

    @staticmethod
    def _short(text: str, limit: int) -> str:
        one_line = " ".join(str(text).split())
        return one_line if len(one_line) <= limit else one_line[:limit] + "…"


class CodingAgentTool(Tool):
    """面向 BrainExecutor 的本地 Coding Agent 适配器。

    实例随 ToolRegistry 常驻并持有可取消 Runner；配置可由设置层刷新。每次 ``run``
    都重新解析目标路径，确保参数无法逃逸已配置 workspace。
    """
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

        startup_timeout = max(
            1, min(60, int(self.options.get("startup_timeout_seconds", 10)))
        )
        total_timeout = max(1, min(600, int(
            self.options.get("total_timeout_seconds",
                             self.options.get("timeout_seconds", 120))
        )))
        no_progress_timeout = max(1, min(300, int(
            self.options.get("no_progress_timeout_seconds",
                             self.options.get("idle_timeout_seconds", 30))
        )))
        prompt = self._prompt(query, operation, target_path)
        args, input_text, env = self._command(provider, executable, prompt)
        protocol = _OpenCodeJsonStream() if provider == "opencode" else None

        def forward(name: str, payload: dict[str, Any]) -> None:
            callback = self.callbacks.get(name)
            # A normal Brain request already travels through generation-checked
            # OutputEvent. Keep the legacy direct callbacks only for callers
            # that did not supply that event path, otherwise the console sees
            # every event twice.
            if callback is not None and on_event is None:
                callback(payload)
            if on_event is None:
                return
            if name == "on_start":
                on_event({
                    "type": "progress", "mode": "TASK_PROGRESS",
                    "content": f"Coding Agent 已启动\nPID: {payload.get('pid')}",
                    "source": source, "tool": self.name, "phase": "running",
                })
            elif name == "on_output_line":
                on_event({
                    "type": "token", "mode": "TASK_STREAM",
                    "content": str(payload.get("line") or ""),
                    "source": str(payload.get("stream") or source),
                    "tool": self.name, "phase": "output",
                })
            elif name == "on_status_change":
                status = str(payload.get("status") or "running")
                on_event({
                    "type": "progress", "mode": "TASK_PROGRESS",
                    "content": str(payload.get("content") or ""),
                    "source": source, "tool": self.name,
                    "phase": "heartbeat" if status == "running" else status,
                })
            elif name == "on_finish":
                on_event({
                    "type": "complete", "mode": "TASK_STREAM", "content": "",
                    "source": source, "tool": self.name,
                    "phase": str(payload.get("status") or "failed"),
                })

        def handle_output(payload: dict[str, Any]) -> None:
            if protocol is None:
                forward("on_output_line", payload)
                return
            for visible in protocol.feed(
                str(payload.get("stream") or "stdout"),
                str(payload.get("line") or ""),
            ):
                forward("on_output_line", visible)

        def handle_status(payload: dict[str, Any]) -> None:
            if str(payload.get("status") or "running") == "running":
                forward("on_status_change", payload)

        process_result = self.runner.run(
            args, str(root), input_text=input_text,
            startup_timeout=startup_timeout,
            total_timeout=total_timeout,
            no_progress_timeout=no_progress_timeout,
            env=env, on_start=lambda payload: forward("on_start", payload),
            on_output_line=handle_output,
            on_status_change=handle_status,
            on_finish=None,
        )
        if protocol is not None:
            for visible in protocol.finish():
                forward("on_output_line", visible)
        base["process"] = self._public_process_result(process_result)
        base["stderr"] = process_result.get("stderr_tail", "")
        status = str(process_result.get("status") or "failed")
        if status != "completed":
            messages = {
                "startup_timeout": "Coding Agent 启动超时，进程未能在期限内启动",
                "startup_failed": "Coding Agent 进程无法启动",
                "total_timeout": "Coding Agent 达到任务总时限，已终止进程树",
                "no_progress_timeout": "Coding Agent 长时间没有输出或状态进展，已终止进程树",
                "needs_setup": "OpenCode 需要配置模型 provider / API Key",
                "cancelled": "用户已取消本次 Coding Agent 任务",
                "failed": "Coding Agent CLI 执行失败",
            }
            forward("on_finish", {"status": status})
            return self._error(base, source, status, messages.get(status, "Coding Agent 执行失败"))
        stdout = str(
            process_result.get("stdout")
            if process_result.get("stdout") is not None
            else process_result.get("stdout_tail") or ""
        )
        final_output = (
            protocol.final_text or self._extract_opencode_text(stdout)
            if protocol is not None else stdout
        )
        self._merge_output(base, final_output)
        forward("on_finish", {"status": status})
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
        return [executable, "run", "--format", "json", prompt], None, env

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
            "parse_status": "not_attempted",
            "parse_error": "",
            "raw_output": "",
        }

    @staticmethod
    def _public_process_result(result: dict[str, Any]) -> dict[str, Any]:
        """Keep diagnostics without sending raw JSONL/tool payloads to Synthesizer."""
        keys = (
            "status", "returncode", "pid", "duration_seconds",
            "last_output_age_seconds", "lines_captured",
            "killed_process_tree", "log_path",
        )
        return {key: result.get(key) for key in keys if key in result}

    @staticmethod
    def _extract_opencode_text(stdout: str) -> str:
        text_parts: list[str] = []
        saw_protocol_event = False
        for line in str(stdout or "").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or "type" not in event:
                continue
            saw_protocol_event = True
            part = event.get("part") if isinstance(event.get("part"), dict) else {}
            if event.get("type") == "text" and part.get("text"):
                text_parts.append(str(part["text"]))
        if text_parts:
            return "\n".join(text_parts).strip()
        # Compatibility for mocked/older OpenCode wrappers that return the
        # requested result object directly rather than JSONL envelopes.
        return "" if saw_protocol_event else str(stdout or "").strip()

    @staticmethod
    def _merge_output(raw: dict[str, Any], stdout: str) -> None:
        output = (stdout or "").strip()
        raw["raw_output"] = output
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", output, re.IGNORECASE | re.DOTALL)
        if fenced:
            output = fenced.group(1).strip()
        try:
            parsed = json.loads(output)
        except (TypeError, json.JSONDecodeError) as exc:
            parsed = None
            decoder = json.JSONDecoder()
            for match in re.finditer(r"\{", output):
                try:
                    candidate, _ = decoder.raw_decode(output[match.start():])
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict):
                    parsed = candidate
                    break
            if parsed is None:
                raw["parse_status"] = "error"
                raw["parse_error"] = f"JSON 解析失败: {exc}"
                return
        if not isinstance(parsed, dict):
            raw["parse_status"] = "error"
            raw["parse_error"] = "JSON 解析失败: 顶层结果不是对象"
            return
        raw["parse_status"] = "parsed"
        raw["parse_error"] = ""
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
