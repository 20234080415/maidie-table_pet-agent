from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from core.brain import BrainRouter
from core.pet import PetController
from core.tools import ToolRegistry
from memory.memory import ConversationMemory
from ui.dialogs import MemorySettingsPage, RecentChatsDialog


class _BlockingMemoryRouter:
    def __init__(self):
        self.extract_started = threading.Event()
        self.release_extract = threading.Event()
        self.clear_calls = 0

    def extract_memories(self, _message, _response):
        self.extract_started.set()
        self.release_extract.wait(2)
        return {
            "facts": [{"key": "name", "value": "stale"}],
            "preferences": [],
        }

    def clear_conversation_state(self):
        self.clear_calls += 1


class _ManualFuture:
    def __init__(self):
        self.complete = False
        self.value = None
        self.cancelled = False

    def done(self):
        return self.complete

    def result(self):
        return self.value

    def cancel(self):
        self.cancelled = True
        return False


class _ManualExecutor:
    def __init__(self):
        self.future = _ManualFuture()

    def submit(self, _function, *_args):
        return self.future


class MemoryClearingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.memory = ConversationMemory(Path(self.temp.name) / "memories.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_running_extraction_cannot_write_back_after_conversation_clear(self):
        router = _BlockingMemoryRouter()
        controller = PetController(router, self.memory, logger=Mock())
        response = {"text": "reply", "source": "chat", "emotion": "idle"}
        controller._on_ai_response_completed("remember me", response, None)
        self.assertTrue(router.extract_started.wait(1))

        self.assertTrue(controller.clear_conversation_history())
        router.release_extract.set()
        deadline = time.monotonic() + 2
        while controller._memory_futures and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(self.memory.get_recent(), [])
        self.assertEqual(self.memory.load_memories(), [])
        controller.shutdown()

    def test_old_ai_request_completion_cannot_save_chat_after_clear(self):
        router = Mock()
        router.clear_conversation_state = Mock()
        controller = PetController(router, self.memory, logger=Mock())
        manual = _ManualExecutor()
        controller.ai_session.executor = manual
        self.assertTrue(controller.ai_session.submit("old request"))

        self.assertTrue(controller.clear_conversation_history())
        manual.future.value = {
            "text": "late reply", "emotion": "idle", "action": "talk",
            "state": "talking", "source": "chat",
        }
        manual.future.complete = True
        controller.ai_session.poll_future()

        self.assertEqual(self.memory.get_recent(), [])
        controller.shutdown()

    def test_conversation_clear_resets_short_term_router_and_search_context(self):
        router = BrainRouter(Mock(), Mock(), ToolRegistry(), self.memory)
        router.intent_router.task_context.event_times["meeting"] = "10:00"
        router.intent_router.last_route = {"intent": "chat"}
        self.memory.set_last_search_query("old query")
        controller = PetController(router, self.memory, logger=Mock())

        self.assertTrue(controller.clear_conversation_history())

        self.assertEqual(router.intent_router.task_context.event_times, {})
        self.assertIsNone(router.intent_router.last_route)
        self.assertEqual(self.memory.get_last_search_query(), "")
        controller.shutdown()

    def test_long_term_clear_preserves_chat_and_short_term_router_context(self):
        self.memory.save("hello", "hi")
        self.memory.save_memory("fact", "name", "Ming")
        router = BrainRouter(Mock(), Mock(), ToolRegistry(), self.memory)
        router.intent_router.task_context.event_times["meeting"] = "10:00"
        controller = PetController(router, self.memory, logger=Mock())

        self.assertTrue(controller.clear_long_term_memory())

        self.assertEqual(len(self.memory.get_recent()), 1)
        self.assertEqual(self.memory.load_memories(), [])
        self.assertEqual(router.intent_router.task_context.event_times, {"meeting": "10:00"})
        controller.shutdown()


class MemoryClearingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_cancel_confirmation_does_not_delete_long_term_memory(self):
        controller = Mock()
        page = MemorySettingsPage(controller)
        with patch("ui.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            page._clear_long_term_memory()
            page._clear_all_memory()
        controller.clear_long_term_memory.assert_not_called()
        controller.clear_all_memory.assert_not_called()
        page.close()

    def test_confirm_calls_correct_long_term_and_all_interfaces(self):
        controller = Mock()
        controller.clear_long_term_memory.return_value = True
        controller.clear_all_memory.return_value = True
        page = MemorySettingsPage(controller)
        with (
            patch("ui.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes),
            patch("ui.dialogs.QMessageBox.information"),
        ):
            page._clear_long_term_memory()
            page._clear_all_memory()
        controller.clear_long_term_memory.assert_called_once_with()
        controller.clear_all_memory.assert_called_once_with()
        page.close()

    def test_delete_failure_shows_warning_instead_of_success(self):
        controller = Mock()
        controller.recent_chats.return_value = [
            {"message": "hello", "response": "hi", "time": "now"}
        ]
        controller.clear_conversation_history.return_value = False
        dialog = RecentChatsDialog(controller)
        with (
            patch("ui.dialogs.QMessageBox.warning") as warning,
            patch("ui.dialogs.QMessageBox.information") as information,
        ):
            dialog._clear()
        warning.assert_called_once()
        information.assert_not_called()
        dialog.close()


if __name__ == "__main__":
    unittest.main()
