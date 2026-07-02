from __future__ import annotations

import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.pet import PetController
from core.session import AISessionCoordinator


class _Future:
    def __init__(self, result=None, error=None, done=True):
        self.value, self.error, self.complete = result, error, done

    def done(self): return self.complete

    def result(self):
        if self.error:
            raise self.error
        return self.value


class _Executor:
    def __init__(self, future): self.future = future
    def submit(self, *_args): return self.future


class _Memory:
    def get_recent(self): return []
    def prompt_context(self): return ""
    def save(self, *_args): pass


class AISessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_session(self, future):
        completed = Mock()
        session = AISessionCoordinator(
            Mock(), _Executor(future), Mock(),
            lambda _message, _proactive: ([], None),
            Mock(), Mock(), completed,
        )
        return session, completed

    def test_pet_controller_submit_delegates_to_session(self):
        controller = PetController(Mock(), _Memory())
        controller.ai_session.submit = Mock()

        controller.submit_text("hello", proactive=True)

        controller.ai_session.submit.assert_called_once_with("hello", True)
        controller.shutdown()

    def test_session_manages_future_lifecycle(self):
        future = _Future({
            "text": "done", "emotion": "idle", "action": "talk",
            "state": "talking", "source": "chat",
        })
        session, _completed = self.make_session(future)

        self.assertTrue(session.submit("hello"))
        self.assertIs(session.future, future)
        session.poll_future()

        self.assertIsNone(session.future)
        self.assertEqual(session.pending_response["text"], "done")
        session.shutdown()

    def test_ai_exception_recovers_busy_state(self):
        session, completed = self.make_session(_Future(error=RuntimeError("offline")))
        session.submit("hello")

        session.poll_future()
        session.complete_stream_response()

        self.assertFalse(session.busy)
        self.assertEqual(completed.call_args.args[1]["emotion"], "sad")
        session.shutdown()

    def test_stream_completion_calls_completion_handler(self):
        session, completed = self.make_session(_Future(done=False))
        session.busy = True
        session.pending_message = "hello"
        session.pending_reaction = "happy"
        session.pending_response = {
            "text": "done", "emotion": "happy", "action": "talk",
            "state": "talking", "source": "chat",
        }

        session.complete_stream_response()

        completed.assert_called_once_with(
            "hello", session.pending_response or {
                "text": "done", "emotion": "happy", "action": "talk",
                "state": "talking", "source": "chat",
            }, "happy",
        )
        self.assertFalse(session.busy)
        session.shutdown()


if __name__ == "__main__":
    unittest.main()
