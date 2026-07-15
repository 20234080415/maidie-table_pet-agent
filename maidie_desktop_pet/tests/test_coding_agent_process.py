from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.tools.coding_agent_process import CodingAgentProcessRunner


class CodingAgentProcessTests(unittest.TestCase):
    def run_agent(self, script: str, root: str, **kwargs):
        options = {
            "startup_timeout": 2,
            "total_timeout": 5,
            "no_progress_timeout": 2,
        }
        options.update(kwargs)
        return CodingAgentProcessRunner().run(
            [sys.executable, "-c", script], root, **options,
        )

    def test_captures_stdout_and_stderr_callbacks(self):
        events = []
        with tempfile.TemporaryDirectory() as root:
            result = self.run_agent(
                "import sys; print('out'); print('err', file=sys.stderr)",
                root,
                on_output_line=events.append,
            )
        self.assertEqual(result["status"], "completed")
        self.assertIn("out", result["stdout_tail"])
        self.assertIn("err", result["stderr_tail"])
        self.assertEqual({item["stream"] for item in events}, {"stdout", "stderr"})

    def test_stdout_without_newline_is_visible_before_process_exits(self):
        received = threading.Event()
        event_times = []
        started = time.monotonic()

        def on_output(payload):
            event_times.append((time.monotonic(), payload))
            received.set()

        with tempfile.TemporaryDirectory() as root:
            result = self.run_agent(
                "import sys,time; sys.stdout.write('working'); sys.stdout.flush(); time.sleep(.8)",
                root,
                on_output_line=on_output,
            )
        self.assertTrue(received.is_set())
        self.assertLess(event_times[0][0] - started, 5)
        self.assertLess(event_times[0][0] - started, result["duration_seconds"])
        self.assertEqual(event_times[0][1]["line"], "working")

    def test_long_running_process_emits_elapsed_status(self):
        statuses = []
        with tempfile.TemporaryDirectory() as root:
            result = self.run_agent(
                "import time; time.sleep(.35)",
                root,
                no_progress_timeout=1,
                progress_interval=.1,
                on_status_change=statuses.append,
            )
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any("正在分析项目" in item.get("content", "") for item in statuses))
        self.assertTrue(any("已运行" in item.get("content", "") for item in statuses))

    def test_startup_timeout_has_distinct_status(self):
        real_popen = subprocess.Popen

        def delayed_popen(*args, **kwargs):
            time.sleep(.2)
            raise OSError("late startup failure")

        with tempfile.TemporaryDirectory() as root, patch(
            "core.tools.coding_agent_process.subprocess.Popen", side_effect=delayed_popen
        ):
            result = CodingAgentProcessRunner().run(
                [sys.executable, "-c", "pass"],
                root,
                startup_timeout=.05,
                total_timeout=2,
                no_progress_timeout=1,
            )
        self.assertEqual(result["status"], "startup_timeout")
        self.assertIn("启动", result["stderr_tail"])
        self.assertIs(subprocess.Popen, real_popen)

    def test_total_timeout_has_distinct_status(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_agent(
                "import time; time.sleep(10)",
                root,
                total_timeout=.2,
                no_progress_timeout=None,
            )
        self.assertEqual(result["status"], "total_timeout")
        self.assertTrue(result["killed_process_tree"])

    def test_no_progress_timeout_has_distinct_status(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_agent(
                "import time; time.sleep(10)",
                root,
                total_timeout=5,
                no_progress_timeout=.2,
            )
        self.assertEqual(result["status"], "no_progress_timeout")
        self.assertTrue(result["killed_process_tree"])

    def test_cancel_kills_parent_and_child_and_stops_callbacks(self):
        runner = CodingAgentProcessRunner()
        holder = {}
        events = []
        with tempfile.TemporaryDirectory() as root:
            pid_file = Path(root) / "child.pid"
            child_code = "import time; time.sleep(30)"
            parent_code = (
                "import pathlib,subprocess,sys,time; "
                f"p=subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
                f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); "
                "sys.stdout.write('started'); sys.stdout.flush(); time.sleep(30)"
            )
            thread = threading.Thread(target=lambda: holder.setdefault(
                "result",
                runner.run(
                    [sys.executable, "-c", parent_code],
                    root,
                    startup_timeout=2,
                    total_timeout=10,
                    no_progress_timeout=10,
                    on_output_line=events.append,
                    on_status_change=events.append,
                    on_finish=events.append,
                ),
            ))
            thread.start()
            deadline = time.monotonic() + 3
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(pid_file.exists())
            child_pid = int(pid_file.read_text())
            runner.cancel()
            event_count_after_cancel = len(events)
            thread.join(5)
            time.sleep(.15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(holder["result"]["status"], "cancelled")
        self.assertTrue(holder["result"]["killed_process_tree"])
        self.assertEqual(len(events), event_count_after_cancel)
        self.assertFalse(self._pid_is_running(holder["result"]["pid"]))
        self.assertFalse(self._pid_is_running(child_pid))

    def test_ansi_terminal_codes_are_removed_from_output(self):
        events = []
        with tempfile.TemporaryDirectory() as root:
            result = self.run_agent(
                "import sys; sys.stdout.buffer.write('\\033[31m分析完成\\033[0m\\n'.encode('utf-8'))",
                root,
                on_output_line=events.append,
            )
        self.assertEqual(result["stdout_tail"], "分析完成")
        self.assertEqual(events[0]["line"], "分析完成\n")

    def test_tail_is_limited_but_complete_output_is_logged(self):
        with tempfile.TemporaryDirectory() as root:
            result = CodingAgentProcessRunner(max_lines=200).run(
                [sys.executable, "-c", "[print(i) for i in range(250)]"],
                root,
                startup_timeout=2,
                total_timeout=5,
                no_progress_timeout=2,
            )
        lines = result["stdout_tail"].splitlines()
        self.assertEqual(len(lines), 200)
        self.assertEqual(lines[0], "50")
        log_path = Path(result["log_path"])
        self.assertTrue(log_path.is_file())
        log_text = log_path.read_text(encoding="utf-8")
        self.assertIn("[stdout] 0", log_text)
        self.assertIn("[stdout] 249", log_text)
        log_path.unlink()

    @patch("core.tools.coding_agent_process.subprocess.Popen")
    def test_popen_is_binary_shell_false_and_cwd_is_workspace(self, popen):
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        stream = os.fdopen(read_fd, "rb", buffering=0)
        process = popen.return_value
        process.pid = 123
        process.stdin = None
        process.stdout = stream
        process.stderr = stream
        process.poll.return_value = 0
        process.wait.return_value = 0
        CodingAgentProcessRunner().run(
            ["tool"],
            "C:/workspace",
            startup_timeout=1,
            total_timeout=1,
            no_progress_timeout=1,
        )
        self.assertIs(popen.call_args.kwargs["shell"], False)
        self.assertEqual(popen.call_args.kwargs["cwd"], "C:/workspace")
        self.assertNotIn("text", popen.call_args.kwargs)

    @staticmethod
    def _pid_is_running(pid: int) -> bool:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in result.stdout and "No tasks" not in result.stdout
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True


if __name__ == "__main__":
    unittest.main()
