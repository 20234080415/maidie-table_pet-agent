from __future__ import annotations

import random
from collections import deque
from typing import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.chat.sentence_splitter import SentenceSplitter


class ChatStreamer(QObject):
    """Buffers LLM deltas and presents complete sentences at a pet-like pace."""

    started = pyqtSignal()
    text_ready = pyqtSignal(str)
    sentence_finished = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        randint: Callable[[int, int], int] = random.randint,
        initial_pause: tuple[int, int] = (120, 360),
        character_pause: tuple[int, int] = (18, 42),
        sentence_pause: tuple[int, int] = (100, 600),
        characters_per_tick: int = 2,
    ) -> None:
        super().__init__(parent)
        self._splitter = SentenceSplitter()
        self._queue: deque[str] = deque()
        self._current = ""
        self._offset = 0
        self._producer_finished = False
        self._active = False
        self._has_output = False
        self._received_text = ""
        self._randint = randint
        self._initial_pause = initial_pause
        self._character_pause = character_pause
        self._sentence_pause = sentence_pause
        self._characters_per_tick = max(1, characters_per_tick)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance)

    @property
    def received_text(self) -> str:
        return self._received_text

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> None:
        self._timer.stop()
        self._splitter.reset()
        self._queue.clear()
        self._current = ""
        self._offset = 0
        self._producer_finished = False
        self._has_output = False
        self._received_text = ""
        self._active = True
        self.started.emit()

    def push_token(self, token: str) -> None:
        if not self._active or not token:
            return
        self._received_text += token
        self._queue.extend(self._splitter.feed(token))
        self._schedule_if_needed(initial=not self._has_output)

    def finish(self) -> None:
        if not self._active:
            return
        remainder = self._splitter.flush()
        if remainder:
            self._queue.append(remainder)
        self._producer_finished = True
        self._schedule_if_needed(initial=not self._has_output)
        self._finish_if_drained()

    def _schedule_if_needed(self, *, initial: bool) -> None:
        if self._timer.isActive() or self._current or not self._queue:
            return
        delay_range = self._initial_pause if initial else self._character_pause
        self._timer.start(self._randint(*delay_range))

    def _advance(self) -> None:
        if not self._current:
            if not self._queue:
                self._finish_if_drained()
                return
            self._current = self._queue.popleft()
            self._offset = 0

        end = min(len(self._current), self._offset + self._characters_per_tick)
        fragment = self._current[self._offset:end]
        self._offset = end
        if fragment:
            self._has_output = True
            self.text_ready.emit(fragment)

        if self._offset >= len(self._current):
            sentence = self._current
            self._current = ""
            self._offset = 0
            self.sentence_finished.emit(sentence)
            if self._queue:
                self._timer.start(self._randint(*self._sentence_pause))
            else:
                self._finish_if_drained()
        else:
            self._timer.start(self._randint(*self._character_pause))

    def _finish_if_drained(self) -> None:
        if self._active and self._producer_finished and not self._queue and not self._current:
            self._active = False
            self.finished.emit()
