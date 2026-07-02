from __future__ import annotations

import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.pet import PetController


class _Memory:
    def get_recent(self): return []
    def prompt_context(self): return ""
    def save(self, _message, _response): pass


class _Future:
    def __init__(self, done=False, result=None, error=None):
        self._done, self._result, self._error = done, result, error

    def done(self): return self._done

    def result(self):
        if self._error:
            raise self._error
        return self._result


class _Executor:
    def __init__(self, future):
        self.future, self.calls = future, []

    def submit(self, function, *args):
        self.calls.append((function, args))
        return self.future

    def shutdown(self, **_kwargs): pass


class ProactiveNonblockingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_controller(self):
        runtime = Mock()
        runtime.engine.enabled = True
        controller = PetController(Mock(), _Memory(), logger=Mock(), proactive_runtime=runtime)
        controller._proactive_timer.stop()
        controller._proactive_poll_timer.stop()
        return controller, runtime

    def test_tick_submits_runtime_instead_of_calling_it(self):
        controller, runtime = self.make_controller()
        executor = _Executor(_Future(done=False))
        controller._proactive_executor.shutdown(wait=False, cancel_futures=True)
        controller._proactive_executor = executor

        controller._proactive_tick()

        runtime.tick.assert_not_called()
        self.assertEqual(executor.calls, [(runtime.tick, ())])
        controller.shutdown()

    def test_tick_does_not_submit_while_future_is_running(self):
        controller, _runtime = self.make_controller()
        executor = _Executor(_Future(done=False))
        controller._proactive_executor.shutdown(wait=False, cancel_futures=True)
        controller._proactive_executor = executor
        controller._proactive_future = executor.future

        controller._proactive_tick()

        self.assertEqual(executor.calls, [])
        controller.shutdown()

    def test_worker_failure_is_logged_without_raising(self):
        controller, _runtime = self.make_controller()
        controller._proactive_future = _Future(done=True, error=RuntimeError("boom"))

        controller._poll_proactive_future()

        controller.logger.exception.assert_called_once_with("Proactive Agent tick failed")
        self.assertIsNone(controller._proactive_future)
        controller.shutdown()

    def test_completed_result_updates_ui_from_completion_entry(self):
        controller, _runtime = self.make_controller()
        decision = Mock(prompt="hello", action="happy")
        controller.submit_text = Mock()

        controller._complete_proactive_result(({"idle_time": 0}, decision))

        controller.submit_text.assert_called_once_with("hello", proactive=True)
        self.assertEqual(controller._pending_reaction, "happy")
        controller.shutdown()


if __name__ == "__main__":
    unittest.main()
