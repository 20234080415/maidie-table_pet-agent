from __future__ import annotations

import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.pet import PetController
from core.session import AISessionCoordinator
from core.session import ThinkingFeedbackPool


class _Future:
    def __init__(self, result=None, error=None, done=True):
        self.value, self.error, self.complete = result, error, done

    def done(self): return self.complete

    def result(self):
        if self.error:
            raise self.error
        return self.value


class _Executor:
    def __init__(self, future): self.future, self.calls = future, []
    def submit(self, *args):
        self.calls.append(args)
        return self.future


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

    def test_thinking_feedback_varies_by_request_context(self):
        pool = ThinkingFeedbackPool(chooser=lambda phrases: phrases[0])
        self.assertEqual(pool.choose("看看我的屏幕"), "让我看看...")
        self.assertEqual(pool.choose("搜索一下 Maidie"), "好啦，我搜索一下...")
        self.assertEqual(pool.choose("今天天气怎么样"), "我看看天气情况...")
        self.assertEqual(pool.choose("CMake 报错"), "我想想...")
        self.assertEqual(pool.choose("帮我完善 Python 测试"), "我看看这段代码...")
        self.assertEqual(pool.choose("你还记得上次的话吗"), "让我回想一下...")
        self.assertGreaterEqual(len(pool.phrases_for("你好")), 8)
        pool_names = (
            "SCREEN", "CURSOR", "SEARCH", "TIME", "WEATHER",
            "CODING", "TECHNICAL", "MEMORY", "CHAT",
        )
        for name in pool_names:
            self.assertTrue(all(
                phrase.endswith("...") for phrase in getattr(pool, name)
            ))

    def test_thinking_feedback_avoids_immediate_context_repeat(self):
        pool = ThinkingFeedbackPool(chooser=lambda phrases: phrases[0])

        first = pool.choose("搜索 Maidie")
        second = pool.choose("搜索 PyQt6")

        self.assertNotEqual(first, second)

    def test_pet_controller_connects_thinking_feedback_to_visible_stream(self):
        controller = PetController(Mock(), _Memory())
        feedback = Mock()
        controller.message_delta.connect(feedback)
        controller.ai_session.executor = _Executor(_Future(done=False))
        controller.ai_session.feedback_pool = ThinkingFeedbackPool(
            chooser=lambda phrases: phrases[0]
        )

        controller.ai_session.submit("搜索一下 Maidie")

        feedback.assert_called_once_with("好啦，我搜索一下...")
        controller.shutdown()

    def test_session_emits_feedback_without_second_ai_request(self):
        feedback = Mock()
        future = _Future(done=False)
        session = AISessionCoordinator(
            Mock(), _Executor(future), Mock(),
            lambda _message, _proactive: ([], None), Mock(), Mock(), Mock(),
            thinking_feedback=feedback,
            feedback_pool=ThinkingFeedbackPool(chooser=lambda phrases: phrases[0]),
        )

        session.submit("现在几点")

        feedback.assert_called_once_with("我看看现在的时间...")
        self.assertEqual(len(session.executor.calls), 1)
        session.shutdown()


if __name__ == "__main__":
    unittest.main()
