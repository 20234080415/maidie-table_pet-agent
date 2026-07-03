from __future__ import annotations

import os
import queue
import subprocess
import threading
from collections import deque
from time import monotonic
from typing import Any, Callable


class CodingAgentProcessRunner:
    SETUP_WORDS = ("api key", "provider", "login", "connect", "auth", "configure", "model")

    def __init__(self, max_lines: int = 200) -> None:
        self.max_lines = max(1, int(max_lines))
        self._process: subprocess.Popen[str] | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    def run(self, args: list[str], cwd: str, *, input_text: str | None = None,
            timeout: float = 120, idle_timeout: float = 30,
            env: dict[str, str] | None = None,
            on_start: Callable[[dict[str, Any]], None] | None = None,
            on_output_line: Callable[[dict[str, Any]], None] | None = None,
            on_status_change: Callable[[dict[str, Any]], None] | None = None,
            on_finish: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        started = monotonic()
        last_output = started
        output_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        stdout_lines: deque[str] = deque(maxlen=self.max_lines)
        stderr_lines: deque[str] = deque(maxlen=self.max_lines)
        all_lines: deque[str] = deque(maxlen=self.max_lines)
        killed = False
        process: subprocess.Popen[str] | None = None
        self._cancel.clear()
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                list(args), cwd=cwd, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", bufsize=1, shell=False, env=env, creationflags=creationflags,
            )
            with self._lock:
                self._process = process
            if on_start:
                on_start({"status": "running", "pid": process.pid, "started_at": started})
            if on_status_change:
                on_status_change({"status": "running"})
            if input_text is not None and process.stdin:
                process.stdin.write(input_text)
                process.stdin.close()

            def read_stream(name: str, stream) -> None:
                try:
                    for line in iter(stream.readline, ""):
                        output_queue.put((name, line.rstrip("\r\n")))
                finally:
                    output_queue.put((name, None))

            threading.Thread(target=read_stream, args=("stdout", process.stdout), daemon=True).start()
            threading.Thread(target=read_stream, args=("stderr", process.stderr), daemon=True).start()
            closed = 0
            status = "completed"
            while True:
                try:
                    stream_name, line = output_queue.get(timeout=0.1)
                    if line is None:
                        closed += 1
                    else:
                        last_output = monotonic()
                        tagged = f"[{stream_name}] {line}"
                        all_lines.append(tagged)
                        (stdout_lines if stream_name == "stdout" else stderr_lines).append(line)
                        if on_output_line:
                            on_output_line({"stream": stream_name, "line": line,
                                            "elapsed_seconds": last_output - started})
                except queue.Empty:
                    pass
                now = monotonic()
                if self._cancel.is_set():
                    status = "cancelled"
                    killed = self._terminate_tree(process.pid)
                    break
                if now - started >= timeout:
                    status = "timeout"
                    killed = self._terminate_tree(process.pid)
                    break
                if now - last_output >= idle_timeout:
                    status = "idle_timeout"
                    killed = self._terminate_tree(process.pid)
                    break
                if process.poll() is not None and closed >= 2:
                    break
            try:
                returncode = process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                killed = self._terminate_tree(process.pid) or killed
                returncode = process.poll()
            combined = "\n".join(all_lines).lower()
            if status == "completed" and returncode != 0:
                status = "needs_setup" if any(word in combined for word in self.SETUP_WORDS) else "failed"
            elif status == "idle_timeout" and any(word in combined for word in self.SETUP_WORDS):
                status = "needs_setup"
            result = {
                "status": status, "returncode": returncode,
                "stdout_tail": "\n".join(stdout_lines), "stderr_tail": "\n".join(stderr_lines),
                "duration_seconds": round(monotonic() - started, 3),
                "last_output_age_seconds": round(monotonic() - last_output, 3),
                "lines_captured": len(all_lines), "killed_process_tree": killed,
            }
        except OSError as exc:
            result = {"status": "failed", "returncode": None, "stdout_tail": "",
                      "stderr_tail": str(exc), "duration_seconds": round(monotonic() - started, 3),
                      "last_output_age_seconds": 0, "lines_captured": 0,
                      "killed_process_tree": False}
        finally:
            with self._lock:
                self._process = None
            if process is not None:
                for stream in (process.stdout, process.stderr, process.stdin):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass
        if on_status_change:
            on_status_change({"status": result["status"]})
        if on_finish:
            on_finish(result)
        return result

    def cancel(self) -> None:
        self._cancel.set()
        with self._lock:
            process = self._process
        if process is not None:
            self._terminate_tree(process.pid)

    shutdown = cancel

    @staticmethod
    def _terminate_tree(pid: int) -> bool:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], shell=False,
                               capture_output=True, timeout=10, check=False)
            else:
                os.killpg(os.getpgid(pid), 15)
            return True
        except (OSError, subprocess.SubprocessError):
            return False
