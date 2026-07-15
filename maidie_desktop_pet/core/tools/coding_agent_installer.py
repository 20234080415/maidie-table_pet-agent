"""探测并通过固定 allowlist 安装本地 OpenCode CLI。

该模块服务于设置/引导流程，不参与日常 Brain Tool 执行；所有安装命令都由受限模板
构造，避免把用户输入拼接为任意 shell，并把过程结果结构化返回给 UI。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Any


class CodingAgentInstaller:
    """通过固定包管理器 allowlist 安装并检查 OpenCode。

    实例可在设置页面操作期间复用；它不保存安装状态，每次从 PATH、配置文件与
    子进程结果重新探测。
    """

    INSTALLERS = {
        "npm": ("npm", "npm.cmd"),
        "scoop": ("scoop", "scoop.cmd"),
        "choco": ("choco", "choco.exe"),
    }

    def __init__(self, timeout_seconds: int = 300) -> None:
        self.timeout_seconds = max(30, min(600, int(timeout_seconds)))

    def detect_install_methods(self) -> dict[str, str]:
        detected: dict[str, str] = {}
        for method, candidates in self.INSTALLERS.items():
            for candidate in candidates:
                executable = shutil.which(candidate)
                if executable:
                    detected[method] = executable
                    break
        return detected

    @staticmethod
    def detect_opencode() -> str:
        for name in ("opencode", "opencode.exe", "opencode.cmd"):
            executable = shutil.which(name)
            if executable:
                return executable
        return ""

    def detect_setup_status(self, workspace_root: str) -> dict[str, Any]:
        root_text = str(workspace_root or "").strip()
        root = Path(root_text).expanduser().resolve() if root_text else None
        config_candidates = [
            Path.home() / ".config" / "opencode" / "opencode.json",
            Path(os.getenv("APPDATA", "")) / "opencode" / "opencode.json",
        ]
        return {
            "installed": bool(self.detect_opencode()),
            "launchable": bool(self.detect_opencode()),
            "provider_config_detected": any(path.is_file() for path in config_candidates),
            "agents_md": bool(root and root.is_dir() and (root / "AGENTS.md").is_file()),
            "workspace_configured": bool(root and root.is_dir()),
        }

    def open_visible_terminal(self, workspace_root: str) -> dict[str, Any]:
        root = Path(str(workspace_root or "")).expanduser().resolve()
        executable = self.detect_opencode()
        if not root.is_dir():
            return {"ok": False, "error": "workspace 未配置或不可用"}
        if not executable:
            return {"ok": False, "error": "未检测到 OpenCode"}
        try:
            if os.name == "nt":
                utf8_command = (
                    "chcp 65001>nul && " + subprocess.list2cmdline([executable])
                )
                windows_terminal = shutil.which("wt.exe") or shutil.which("wt")
                if windows_terminal:
                    args = [
                        windows_terminal, "-w", "new", "new-tab",
                        "--startingDirectory", str(root),
                        "cmd.exe", "/d", "/k", utf8_command,
                    ]
                    creationflags = 0
                    terminal = "windows_terminal"
                else:
                    args = ["cmd.exe", "/d", "/k", utf8_command]
                    creationflags = subprocess.CREATE_NEW_CONSOLE
                    terminal = "cmd"
                process = subprocess.Popen(
                    args, cwd=str(root), shell=False,
                    creationflags=creationflags,
                )
            else:
                process = subprocess.Popen([executable], cwd=str(root), shell=False)
                terminal = "default"
            return {"ok": True, "pid": process.pid, "terminal": terminal}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def build_install_command(self, method: str) -> list[str]:
        normalized = str(method or "").strip().lower()
        executable = self.detect_install_methods().get(normalized)
        if not executable:
            raise ValueError(f"安装方式不可用: {normalized or 'unknown'}")
        if normalized == "npm":
            return [executable, "install", "-g", "opencode-ai"]
        if normalized == "scoop":
            return [executable, "install", "opencode"]
        if normalized == "choco":
            return [executable, "install", "opencode", "-y"]
        raise ValueError("不支持的安装方式")

    def install_opencode(self, method: str) -> dict[str, Any]:
        try:
            command = self.build_install_command(method)
        except ValueError as exc:
            return self._result(False, method, error=str(exc))
        try:
            completed = subprocess.run(
                command,
                cwd=tempfile.gettempdir(),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self.timeout_seconds,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return self._result(
                False, method, stdout=self._output(exc.stdout), stderr=self._output(exc.stderr),
                error=f"安装超时（{self.timeout_seconds} 秒）",
            )
        except OSError as exc:
            return self._result(False, method, error=f"安装命令无法启动: {exc}")

        command_path = self.detect_opencode()
        success = completed.returncode == 0 and bool(command_path)
        error = ""
        if completed.returncode != 0:
            error = f"安装命令失败，退出码 {completed.returncode}"
        elif not command_path:
            error = "安装命令已完成，但重新检测后仍未找到 opencode"
        return self._result(
            success, method, stdout=completed.stdout, stderr=completed.stderr,
            error=error, returncode=completed.returncode, command_path=command_path,
        )

    @staticmethod
    def _output(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value or "")

    @staticmethod
    def _result(success: bool, method: str, stdout: str = "", stderr: str = "",
                error: str = "", returncode: int | None = None,
                command_path: str = "") -> dict[str, Any]:
        return {
            "success": success,
            "method": str(method or ""),
            "stdout": str(stdout or ""),
            "stderr": str(stderr or ""),
            "error": str(error or ""),
            "returncode": returncode,
            "command_path": str(command_path or ""),
        }
