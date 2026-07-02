from __future__ import annotations

import os
import unittest
from time import monotonic
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.pet import PetController


class _Memory:
    def get_recent(self):
        return []

    def prompt_context(self):
        return ""

    def save(self, _message, _response):
        pass


class SubmitResponsivenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_submit_does_not_route_on_the_qt_thread(self):
        router = Mock()
        router.classify.side_effect = AssertionError("synchronous router call")
        router.ask_stream.return_value = {
            "text": "好。",
            "emotion": "idle",
            "action": "talk",
            "state": "talking",
            "source": "chat",
        }
        controller = PetController(router, _Memory())
        started = monotonic()

        controller.submit_text("你好")

        self.assertLess(monotonic() - started, 0.1)
        router.classify.assert_not_called()
        controller.shutdown()


if __name__ == "__main__":
    unittest.main()
