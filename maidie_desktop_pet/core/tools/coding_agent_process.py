"""Run a local Coding Agent process with bounded, observable lifecycle semantics."""

from __future__ import annotations

import codecs
import os
import queue
import subprocess
import tempfile
import threading
from collections import deque
from time import monotonic
from typing import Any, BinaryIO, Callable, TextIO


class _AnsiCleaner:
    """Remove CSI/OSC terminal sequences even when they span byte chunks."""

    def __init__(self) -> None:
        self._state = "text"

    def feed(self, text: str) -> str:
        output: list[str] = []
        for char in text:
            if self._state == "text":
                if char == "\x1b":
                    self._state = "escape"
                elif char != "\r":
                    output.append(char)
            elif self._state == "escape":
                if char == "[":
                    self._state = "csi"
                elif char == "]":
                    self._state = "osc"
                elif "@" <= char <= "_":
                    self._state = "text"
                else:
                    self._state = "text"
            elif self._state == "csi":
                if "@" <= char <= "~":
                    self._state = "text"
            elif self._state == "osc":
                if char == "\x07":
                    self._state = "text"
                elif char == "\x1b":
                    self._state = "osc_escape"
            elif self._state == "osc_escape":
                self._state = "text" if char == "\\" else "osc"
        return "".join(output)


class _TailBuffer:
    """Keep only the most recent logical lines while accepting partial chunks."""

    def __init__(self, max_lines: int) -> None:
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._partial = ""
        self.total_lines = 0

    def feed(self, text: str) -> None:
        if not text:
            return
        parts = (self._partial + text).splitlines(keepends=True)
        self._partial = ""
        for part in parts:
            if part.endswith(("\n", "\r")):
                self._lines.append(part.rstrip("\r\n"))
                self.total_lines += 1
            else:
                self._partial = part

    def text(self) -> str:
        lines = list(self._lines)
        if self._partial:
            lines.append(self._partial)
        return "\n".join(lines[-self._lines.maxlen:])


class CodingAgentProcessRunner:
    """Manage one CLI process, byte-stream output, timeouts and tree cleanup."""

    SETUP_WORDS = ("api key", "provider", "login", "connect", "auth", "configure", "model")

    def __init__(self, max_lines: int = 200) -> None:
        self.max_lines = max(1, int(max_lines))
        self._process: subprocess.Popen[bytes] | None = None
        self._cancel = threading.Event()
        self._cancel_killed = False
        self._lock = threading.Lock()

    def run(
        self,
        args: list[str],
        cwd: str,
        *,
        input_text: str | None = None,
        startup_timeout: float = 10,
        total_timeout: float = 120,
        no_progress_timeout: float | None = 30,
        progress_interval: float = 5,
        env: dict[str, str] | None = None,
        on_start: Callable[[dict[str, Any]], None] | None = None,
        on_output_line: Callable[[dict[str, Any]], None] | None = None,
        on_status_change: Callable[[dict[str, Any]], None] | None = None,
        on_finish: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Run validated argv with separate startup, total and progress deadlines.

        Output callbacks are chunk-based despite the compatibility name
        ``on_output_line``. A flushed byte sequence is progress even without a
        newline, and stdout/stderr are decoded independently and incrementally.
        """
        run_started = monotonic()
        last_progress = run_started
        last_status = run_started
        output_queue: queue.Queue[tuple[str, bytes | None]] = queue.Queue()
        stdout_tail = _TailBuffer(self.max_lines)
        stderr_tail = _TailBuffer(self.max_lines)
        stdout_spool = tempfile.SpooledTemporaryFile(
            max_size=1024 * 1024, mode="w+t", encoding="utf-8", newline=""
        )
        stderr_spool = tempfile.SpooledTemporaryFile(
            max_size=1024 * 1024, mode="w+t", encoding="utf-8", newline=""
        )
        log_file = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False,
            prefix="maidie-coding-agent-", suffix=".log",
        )
        process: subprocess.Popen[bytes] | None = None
        killed = False
        self._cancel.clear()
        self._cancel_killed = False

        try:
            process, startup_error = self._start_process(
                args,
                cwd,
                input_text=input_text,
                env=env,
                startup_timeout=max(0.01, float(startup_timeout)),
            )
            if process is None:
                status = "cancelled" if self._cancel.is_set() else (
                    "startup_timeout" if startup_error is None else "startup_failed"
                )
                error = (
                    "Coding Agent 启动超时"
                    if status == "startup_timeout"
                    else str(startup_error or "Coding Agent 启动已取消")
                )
                result = self._result(
                    status=status,
                    returncode=None,
                    stdout="",
                    stderr=error,
                    stdout_tail="",
                    stderr_tail=error,
                    run_started=run_started,
                    last_progress=last_progress,
                    lines_captured=0,
                    killed=False,
                    log_path=log_file.name,
                    pid=None,
                )
                log_file.write(f"[runner] {error}\n")
                return self._finish_callbacks(result, on_status_change, on_finish)

            with self._lock:
                self._process = process
            last_progress = monotonic()
            if on_start:
                on_start({
                    "status": "running",
                    "pid": process.pid,
                    "started_at": run_started,
                    "content": f"Coding Agent 已启动\nPID: {process.pid}",
                })
            if on_status_change:
                on_status_change({
                    "status": "running",
                    "content": "正在分析项目...\n已运行 0 秒",
                    "elapsed_seconds": 0,
                })

            self._write_stdin(process, input_text)
            for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
                threading.Thread(
                    target=self._read_stream,
                    args=(name, stream, output_queue),
                    daemon=True,
                    name=f"coding-agent-{name}",
                ).start()

            decoders = {
                "stdout": codecs.getincrementaldecoder("utf-8")("replace"),
                "stderr": codecs.getincrementaldecoder("utf-8")("replace"),
            }
            cleaners = {"stdout": _AnsiCleaner(), "stderr": _AnsiCleaner()}
            spools: dict[str, TextIO] = {"stdout": stdout_spool, "stderr": stderr_spool}
            tails = {"stdout": stdout_tail, "stderr": stderr_tail}
            closed_streams = 0
            output_chunks = 0
            status = "completed"

            while True:
                now = monotonic()
                if self._cancel.is_set():
                    status = "cancelled"
                    killed = self._cancel_killed or self._terminate_tree(process.pid)
                    break
                if now - run_started >= total_timeout:
                    status = "total_timeout"
                    killed = self._terminate_tree(process.pid)
                    break
                if (no_progress_timeout is not None
                        and now - last_progress >= no_progress_timeout):
                    status = "no_progress_timeout"
                    killed = self._terminate_tree(process.pid)
                    break

                try:
                    stream_name, data = output_queue.get(timeout=0.05)
                except queue.Empty:
                    data = b""
                    stream_name = ""

                if self._cancel.is_set():
                    status = "cancelled"
                    killed = self._cancel_killed or self._terminate_tree(process.pid)
                    break
                if stream_name:
                    if data is None:
                        closed_streams += 1
                        final_text = cleaners[stream_name].feed(
                            decoders[stream_name].decode(b"", final=True)
                        )
                        if final_text:
                            self._record_output(
                                stream_name, final_text, spools[stream_name],
                                tails[stream_name], log_file,
                            )
                    else:
                        text = cleaners[stream_name].feed(decoders[stream_name].decode(data))
                        last_progress = monotonic()
                        output_chunks += 1
                        if text:
                            self._record_output(
                                stream_name, text, spools[stream_name],
                                tails[stream_name], log_file,
                            )
                            if on_output_line and not self._cancel.is_set():
                                on_output_line({
                                    "stream": stream_name,
                                    "line": text,
                                    "elapsed_seconds": last_progress - run_started,
                                })

                now = monotonic()
                if (on_status_change and not self._cancel.is_set()
                        and now - last_status >= max(0.05, progress_interval)):
                    elapsed = int(now - run_started)
                    on_status_change({
                        "status": "running",
                        "content": f"正在分析项目...\n已运行 {elapsed} 秒",
                        "elapsed_seconds": elapsed,
                    })
                    last_status = now
                if process.poll() is not None and closed_streams >= 2:
                    break

            try:
                returncode = process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                killed = self._terminate_tree(process.pid) or killed
                returncode = process.poll()

            stdout = self._read_spool(stdout_spool)
            stderr = self._read_spool(stderr_spool)
            combined = f"{stdout}\n{stderr}".lower()
            if status == "completed" and returncode != 0:
                status = "needs_setup" if any(
                    word in combined for word in self.SETUP_WORDS
                ) else "failed"
            result = self._result(
                status=status,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                stdout_tail=stdout_tail.text(),
                stderr_tail=stderr_tail.text(),
                run_started=run_started,
                last_progress=last_progress,
                lines_captured=(stdout_tail.total_lines + stderr_tail.total_lines + output_chunks),
                killed=killed,
                log_path=log_file.name,
                pid=process.pid,
            )
            return self._finish_callbacks(result, on_status_change, on_finish)
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
            log_file.close()
            stdout_spool.close()
            stderr_spool.close()

    def _start_process(
        self,
        args: list[str],
        cwd: str,
        *,
        input_text: str | None,
        env: dict[str, str] | None,
        startup_timeout: float,
    ) -> tuple[subprocess.Popen[bytes] | None, BaseException | None]:
        result_queue: queue.Queue[tuple[subprocess.Popen[bytes] | None, BaseException | None]] = queue.Queue()
        abandoned = threading.Event()

        def start() -> None:
            try:
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                created = subprocess.Popen(
                    list(args),
                    cwd=cwd,
                    stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                    shell=False,
                    env=env,
                    creationflags=creationflags,
                    start_new_session=os.name != "nt",
                )
            except BaseException as exc:  # passed back to the owning thread
                result_queue.put((None, exc))
                return
            if abandoned.is_set() or self._cancel.is_set():
                self._terminate_tree(created.pid)
                self._close_process_streams(created)
                return
            result_queue.put((created, None))

        threading.Thread(target=start, daemon=True, name="coding-agent-start").start()
        deadline = monotonic() + startup_timeout
        while monotonic() < deadline:
            if self._cancel.is_set():
                abandoned.set()
                return None, None
            try:
                return result_queue.get(timeout=min(0.05, max(0.001, deadline - monotonic())))
            except queue.Empty:
                pass
        abandoned.set()
        return None, None

    @staticmethod
    def _write_stdin(process: subprocess.Popen[bytes], input_text: str | None) -> None:
        if input_text is None or process.stdin is None:
            return
        process.stdin.write(input_text.encode("utf-8"))
        process.stdin.close()

    @staticmethod
    def _read_stream(
        name: str,
        stream: BinaryIO | None,
        output_queue: queue.Queue[tuple[str, bytes | None]],
    ) -> None:
        try:
            if stream is None:
                return
            descriptor = stream.fileno()
            while True:
                chunk = os.read(descriptor, 4096)
                if not chunk:
                    break
                output_queue.put((name, chunk))
        except (OSError, ValueError):
            pass
        finally:
            output_queue.put((name, None))

    @staticmethod
    def _record_output(
        stream_name: str,
        text: str,
        spool: TextIO,
        tail: _TailBuffer,
        log_file: TextIO,
    ) -> None:
        spool.write(text)
        tail.feed(text)
        tagged = text.replace("\n", f"\n[{stream_name}] ")
        log_file.write(f"[{stream_name}] {tagged}")
        if not text.endswith("\n"):
            log_file.write("\n")
        log_file.flush()

    @staticmethod
    def _read_spool(spool: TextIO) -> str:
        spool.flush()
        spool.seek(0)
        return spool.read()

    @staticmethod
    def _result(
        *,
        status: str,
        returncode: int | None,
        stdout: str,
        stderr: str,
        stdout_tail: str,
        stderr_tail: str,
        run_started: float,
        last_progress: float,
        lines_captured: int,
        killed: bool,
        log_path: str,
        pid: int | None,
    ) -> dict[str, Any]:
        now = monotonic()
        return {
            "status": status,
            "returncode": returncode,
            "pid": pid,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "duration_seconds": round(now - run_started, 3),
            "last_output_age_seconds": round(now - last_progress, 3),
            "lines_captured": lines_captured,
            "killed_process_tree": killed,
            "log_path": log_path,
        }

    def _finish_callbacks(
        self,
        result: dict[str, Any],
        on_status_change: Callable[[dict[str, Any]], None] | None,
        on_finish: Callable[[dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        if result["status"] != "cancelled":
            if on_status_change:
                on_status_change({"status": result["status"], "content": ""})
            if on_finish:
                on_finish(result)
        return result

    def cancel(self) -> None:
        with self._lock:
            process = self._process
            self._cancel_killed = process is not None or self._cancel_killed
        self._cancel.set()
        if process is not None:
            killed = self._terminate_tree(process.pid)
            with self._lock:
                self._cancel_killed = killed or self._cancel_killed

    shutdown = cancel

    @staticmethod
    def _close_process_streams(process: subprocess.Popen[bytes]) -> None:
        for stream in (process.stdout, process.stderr, process.stdin):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    @staticmethod
    def _terminate_tree(pid: int) -> bool:
        try:
            if os.name == "nt":
                completed = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    shell=False,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                return completed.returncode == 0
            os.killpg(os.getpgid(pid), 15)
            return True
        except (OSError, subprocess.SubprocessError):
            return False
