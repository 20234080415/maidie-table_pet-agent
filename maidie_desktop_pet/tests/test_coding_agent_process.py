from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.tools.coding_agent_process import CodingAgentProcessRunner


class CodingAgentProcessTests(unittest.TestCase):
    def test_captures_streams_and_line_callbacks(self):
        events = []
        with tempfile.TemporaryDirectory() as root:
            result = CodingAgentProcessRunner().run(
                [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
                root, timeout=5, idle_timeout=2, on_output_line=events.append,
            )
        self.assertEqual(result["status"], "completed")
        self.assertIn("out", result["stdout_tail"])
        self.assertIn("err", result["stderr_tail"])
        self.assertEqual({item["stream"] for item in events}, {"stdout", "stderr"})

    def test_ansi_terminal_codes_are_removed_from_output(self):
        events = []
        with tempfile.TemporaryDirectory() as root:
            result = CodingAgentProcessRunner().run(
                [sys.executable, "-c",
                 "import sys; sys.stdout.buffer.write('\\033[31m分析完成\\033[0m\\n'.encode('utf-8'))"],
                root, timeout=5, idle_timeout=2, on_output_line=events.append,
            )
        self.assertEqual(result["stdout_tail"], "分析完成")
        self.assertEqual(events[0]["line"], "分析完成")

    def test_idle_timeout_can_be_disabled_for_quiet_tui_work(self):
        with tempfile.TemporaryDirectory() as root:
            result = CodingAgentProcessRunner().run(
                [sys.executable, "-c", "import time; time.sleep(.3); print('done')"],
                root, timeout=2, idle_timeout=None,
            )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["stdout_tail"], "done")

    def test_idle_timeout_kills_process_tree(self):
        with tempfile.TemporaryDirectory() as root:
            result = CodingAgentProcessRunner().run(
                [sys.executable, "-c", "import time; time.sleep(10)"], root,
                timeout=5, idle_timeout=.2,
            )
        self.assertEqual(result["status"], "idle_timeout")
        self.assertTrue(result["killed_process_tree"])

    def test_cancel_kills_process_tree(self):
        runner = CodingAgentProcessRunner(); holder = {}
        with tempfile.TemporaryDirectory() as root:
            thread = threading.Thread(target=lambda: holder.setdefault("result", runner.run(
                [sys.executable, "-c", "import time; print('start', flush=True); time.sleep(10)"],
                root, timeout=5, idle_timeout=5)))
            thread.start(); time.sleep(.2); runner.cancel(); thread.join(5)
        self.assertEqual(holder["result"]["status"], "cancelled")
        self.assertTrue(holder["result"]["killed_process_tree"])

    def test_tail_is_limited(self):
        with tempfile.TemporaryDirectory() as root:
            result = CodingAgentProcessRunner(max_lines=200).run(
                [sys.executable, "-c", "[print(i) for i in range(250)]"], root,
                timeout=5, idle_timeout=2)
        lines = result["stdout_tail"].splitlines()
        self.assertEqual(len(lines), 200)
        self.assertEqual(lines[0], "50")

    @patch("core.tools.coding_agent_process.subprocess.Popen")
    def test_popen_is_shell_false_and_cwd_is_workspace(self, popen):
        process = Mock(pid=123, stdin=None)
        process.stdout.readline.return_value = ""; process.stderr.readline.return_value = ""
        process.poll.return_value = 0; process.wait.return_value = 0; popen.return_value = process
        CodingAgentProcessRunner().run(["tool"], "C:/workspace", timeout=1, idle_timeout=1)
        self.assertIs(popen.call_args.kwargs["shell"], False)
        self.assertEqual(popen.call_args.kwargs["cwd"], "C:/workspace")


if __name__ == "__main__": unittest.main()
