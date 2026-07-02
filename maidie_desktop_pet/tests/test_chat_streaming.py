from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QAbstractAnimation, QElapsedTimer, QEvent, QPointF, Qt, QTimer
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from core.chat.chat_streamer import ChatStreamer
from core.chat.sentence_splitter import SentenceSplitter
from core.pet import PetController
from core.state import PetState
from ui.bubble import SpeechBubble
from ui.window import PetWindow


class _Memory:
    def __init__(self):
        self.saved = []

    def get_recent(self):
        return []

    def clear(self):
        pass

    def save(self, message, response):
        self.saved.append((message, response))


class _Router:
    def classify(self, _message):
        return "chat"


class SentenceSplitterTests(unittest.TestCase):
    def test_splits_across_arbitrary_token_boundaries(self):
        splitter = SentenceSplitter()
        self.assertEqual(splitter.feed("让我看"), [])
        self.assertEqual(splitter.feed("看。可以"), ["让我看看。"])
        self.assertEqual(splitter.feed("！Really?"), ["可以！", "Really?"])
        self.assertEqual(splitter.flush(), "")

    def test_flush_returns_unterminated_tail(self):
        splitter = SentenceSplitter()
        splitter.feed("嗯，这样更好")
        self.assertEqual(splitter.flush(), "嗯，这样更好")


class StreamingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _wait_until(self, predicate, timeout_ms=1000):
        elapsed = QElapsedTimer()
        elapsed.start()
        while not predicate() and elapsed.elapsed() < timeout_ms:
            self.app.processEvents()
        self.assertTrue(predicate())

    def test_streamer_paces_sentences_without_blocking_event_loop(self):
        streamer = ChatStreamer(
            randint=lambda low, _high: low,
            initial_pause=(0, 0),
            character_pause=(0, 0),
            sentence_pause=(0, 0),
            characters_per_tick=2,
        )
        fragments: list[str] = []
        sentences: list[str] = []
        done: list[bool] = []
        event_loop_tick: list[bool] = []
        streamer.text_ready.connect(fragments.append)
        streamer.sentence_finished.connect(sentences.append)
        streamer.finished.connect(lambda: done.append(True))

        streamer.start()
        streamer.push_token("你好")
        streamer.push_token("。再见!")
        QTimer.singleShot(0, lambda: event_loop_tick.append(True))
        streamer.finish()
        self._wait_until(lambda: bool(done))

        self.assertEqual("".join(fragments), "你好。再见!")
        self.assertEqual(sentences, ["你好。", "再见!"])
        self.assertTrue(event_loop_tick)

    def test_bubble_inserts_fragments_into_existing_document(self):
        bubble = SpeechBubble()
        bubble.begin_stream()
        bubble.append_text("让我")
        first_document = bubble.document()
        bubble.append_text("看看。")

        self.assertIs(bubble.document(), first_document)
        self.assertEqual(bubble.toPlainText(), "让我看看。")
        bubble.close()

    def test_bubble_expands_smoothly_from_its_current_size(self):
        bubble = SpeechBubble()
        bubble.begin_stream()
        initial_size = bubble.size()
        bubble.append_text("这是一段会让气泡先横向舒展，然后自然向下长高的文字。")
        target_size = bubble._size_animation.endValue()

        self.assertEqual(
            bubble._size_animation.state(), QAbstractAnimation.State.Running
        )
        self.assertNotEqual(initial_size, target_size)
        self._wait_until(
            lambda: bubble._size_animation.state() == QAbstractAnimation.State.Stopped
        )
        self.assertEqual(bubble.size(), target_size)
        bubble.close()

    def test_first_visible_fragment_syncs_speaking_animation(self):
        controller = PetController(_Router(), _Memory())
        emotions: list[str] = []
        animations: list[str] = []
        controller.emotion_changed.connect(emotions.append)
        controller.animation_changed.connect(animations.append)

        controller._present_stream_text("你")

        self.assertEqual(controller.state, PetState.TALKING)
        self.assertEqual(emotions, ["speaking"])
        self.assertEqual(animations, ["talking"])
        controller.shutdown()

    def test_response_completes_only_after_paced_output(self):
        memory = _Memory()
        controller = PetController(_Router(), memory)
        controller.chat_streamer._initial_pause = (0, 0)
        controller.chat_streamer._character_pause = (0, 0)
        controller.chat_streamer._sentence_pause = (0, 0)
        controller.chat_streamer._characters_per_tick = 20
        visible: list[str] = []
        completed: list[dict] = []
        emotions: list[str] = []
        controller.message_delta.connect(visible.append)
        controller.message_received.connect(completed.append)
        controller.emotion_changed.connect(emotions.append)
        controller._busy = True
        controller._pending_message = "你好"
        controller._pending_source = "chat"
        controller.chat_streamer.start()

        controller._handle_stream_delta("让我看看。")
        controller._handle_result({
            "text": "让我看看。",
            "emotion": "idle",
            "action": "talk",
            "state": "talking",
            "source": "chat",
        })
        self.assertEqual(completed, [])
        self._wait_until(lambda: bool(completed))

        self.assertEqual("".join(visible), "让我看看。")
        self.assertEqual(emotions, ["speaking", "idle"])
        self.assertEqual(controller.state, PetState.IDLE)
        self.assertEqual(memory.saved, [("你好", "让我看看。")])
        controller.shutdown()

    def test_double_click_cancels_pending_single_click_action(self):
        controller = PetController(_Router(), _Memory())
        controller.on_pet_clicked = Mock()
        controller.on_headpat = Mock()
        controller.on_facepoke = Mock()
        window = PetWindow(controller, Path(__file__).parents[1] / "assets")
        window.show()
        window._pending_click_region = "body"
        window._single_click_timer.start(20)
        double_click = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            QPointF(20, 20),
            QPointF(20, 20),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(20, 20),
            QPointF(20, 20),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

        window.mouseDoubleClickEvent(double_click)
        window.mouseReleaseEvent(release)
        QTest.qWait(60)

        controller.on_pet_clicked.assert_not_called()
        controller.on_headpat.assert_not_called()
        controller.on_facepoke.assert_not_called()
        self.assertIsNone(window._pending_click_region)
        window.close()


if __name__ == "__main__":
    unittest.main()
