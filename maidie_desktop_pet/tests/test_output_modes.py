from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.brain.executor import BrainExecutor
from core.brain.synthesizer import Synthesizer
from core.pet import PetController
from core.session.ai_session import AISessionCoordinator
from core.session.output_events import OutputEvent, OutputMode
from ui.window import PetWindow


class _Executor:
    def submit(self, *_args):
        return Mock()


class _Model:
    api_key = "configured"

    def ask(self, _prompt, _context):
        return {"text": "answer", "emotion": "idle", "action": "talk",
                "state": "talking"}


class _Memory:
    def __init__(self): self.saved = []
    def get_recent(self): return []
    def prompt_context(self): return ""
    def save(self, *args): self.saved.append(args)


class OutputModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_session(self):
        visible = Mock()
        completed = Mock()
        events = []
        session = AISessionCoordinator(
            Mock(), _Executor(), Mock(), lambda *_args: ([], None),
            visible, Mock(), completed, output_event=events.append,
        )
        session.request_id = "current"
        session._request_generation = 2
        session.streamer.start()
        return session, visible, completed, events

    def test_three_output_modes_exist(self):
        self.assertEqual(OutputMode.CHAT_NATURAL.value, "CHAT_NATURAL")
        self.assertEqual(OutputMode.TASK_STREAM.value, "TASK_STREAM")
        self.assertEqual(OutputMode.TASK_PROGRESS.value, "TASK_PROGRESS")

    def test_event_contains_complete_contract(self):
        event = OutputEvent(
            request_id="request", generation=3, sequence=4,
            type="token", mode=OutputMode.TASK_STREAM, content="result",
            source="tool", tool="search", phase="running",
        ).to_dict()

        self.assertEqual(set(event), {
            "request_id", "generation", "sequence", "type", "mode",
            "content", "source", "tool", "phase",
        })
        self.assertEqual(event["mode"], "TASK_STREAM")

    def test_old_generation_drops_token_progress_and_complete(self):
        session, visible, _completed, events = self.make_session()

        for kind, mode in (
            ("token", OutputMode.CHAT_NATURAL),
            ("progress", OutputMode.TASK_PROGRESS),
            ("complete", OutputMode.TASK_STREAM),
        ):
            session.accept_output_event(
                {"type": kind, "mode": mode.value, "content": kind},
                request_id="old", generation=1,
            )

        visible.assert_not_called()
        self.assertEqual(events, [])
        self.assertEqual(session.streamer.received_text, "")
        session.shutdown()

    def test_cancel_rejects_late_events(self):
        session, visible, _completed, events = self.make_session()
        old_generation = session._request_generation
        session.invalidate_current_request()
        events.clear()

        session.accept_output_event(
            {"type": "token", "mode": "TASK_STREAM", "content": "late"},
            request_id="current", generation=old_generation,
        )

        visible.assert_not_called()
        self.assertEqual(events, [])
        session.shutdown()

    def test_chat_natural_enters_speech_player(self):
        session, _visible, _completed, events = self.make_session()

        session.accept_output_event(
            {"type": "token", "mode": "CHAT_NATURAL", "content": "hello"},
            request_id="current", generation=2,
        )

        self.assertEqual(session.streamer.received_text, "hello")
        self.assertEqual(events, [])
        session.shutdown()

    def test_task_stream_bypasses_speech_player(self):
        session, _visible, _completed, events = self.make_session()

        session.accept_output_event(
            {"type": "token", "mode": "TASK_STREAM", "content": "result"},
            request_id="current", generation=2,
        )

        self.assertEqual(session.streamer.received_text, "")
        self.assertEqual(events[-1]["content"], "result")
        self.assertEqual(events[-1]["mode"], "TASK_STREAM")
        session.shutdown()

    def test_task_progress_does_not_complete_or_persist_response(self):
        session, _visible, completed, events = self.make_session()

        session.accept_output_event(
            {"type": "progress", "mode": "TASK_PROGRESS",
             "content": "正在搜索...", "tool": "search", "phase": "running"},
            request_id="current", generation=2,
        )

        completed.assert_not_called()
        self.assertIsNone(session.pending_response)
        self.assertEqual(events[-1]["type"], "progress")
        session.shutdown()

    def test_executor_emits_progress_for_search_file_and_coding_tasks(self):
        cases = (
            ("search", {"query": "docs"}, "正在搜索..."),
            ("system", {"operation": "read_file", "path": "demo.txt"},
             "正在读取文件..."),
            ("coding_agent", {"operation": "analyze_project"}, "正在分析项目..."),
        )
        for tool_name, params, expected in cases:
            with self.subTest(tool=tool_name):
                tool = Mock()
                tool.run.return_value = {
                    "type": tool_name, "raw": {}, "source": "local",
                }
                tool.execute.return_value = {
                    "type": tool_name, "raw": {}, "source": "local",
                }
                registry = Mock()
                registry.get.return_value = tool
                events = []

                BrainExecutor(registry).execute(
                    {"steps": [{"tool": tool_name, "params": params}]},
                    "request", on_event=events.append,
                )

                self.assertEqual(events[0]["type"], "progress")
                self.assertEqual(events[0]["mode"], "TASK_PROGRESS")
                self.assertEqual(events[0]["content"], expected)
                self.assertEqual(events[0]["tool"], tool_name)
                self.assertEqual(events[0]["phase"], "running")

    def test_synthesizer_labels_chat_and_task_tokens(self):
        chat_events = []
        chat = Synthesizer(_Model()).synthesize(
            "hello", "chat", None, [], "", [], on_delta=chat_events.append,
            output_mode=OutputMode.CHAT_NATURAL,
        )
        task_events = []
        task = Synthesizer(_Model()).synthesize(
            "search", "tool", {}, [{
                "tool": "search", "ok": True,
                "data": {"raw": {"sources": []}},
            }], "", [], on_delta=task_events.append,
            output_mode=OutputMode.TASK_STREAM,
        )

        self.assertEqual(chat["output_mode"], "CHAT_NATURAL")
        self.assertEqual(chat_events[-1]["mode"], "CHAT_NATURAL")
        self.assertEqual(task["output_mode"], "TASK_STREAM")
        self.assertEqual(task_events[-1]["mode"], "TASK_STREAM")

    def test_task_events_update_ui_without_speech_or_history(self):
        memory = _Memory()
        controller = PetController(Mock(), memory)
        window = PetWindow(controller, Path(__file__).resolve().parents[1] / "assets")
        session = controller.ai_session
        session.request_id = "task"
        session._request_generation = 1
        session.streamer.start()

        session.accept_output_event(
            {"type": "progress", "mode": "TASK_PROGRESS",
             "content": "正在搜索...", "tool": "search", "phase": "running"},
            request_id="task", generation=1,
        )
        self.assertIn("正在搜索", window.bubble.toPlainText())
        session.accept_output_event(
            {"type": "token", "mode": "TASK_STREAM", "content": "result",
             "source": "tool", "tool": "search", "phase": "streaming"},
            request_id="task", generation=1,
        )

        self.assertEqual(window.bubble.toPlainText(), "result")
        self.assertEqual(session.streamer.received_text, "")
        self.assertEqual(memory.saved, [])
        window.shutdown()
        window.close()


if __name__ == "__main__":
    unittest.main()
