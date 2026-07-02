from __future__ import annotations

import random
import re
from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


@dataclass(frozen=True)
class SpeechSegment:
    text: str
    pause_after_ms: int = 260
    emotion: str | None = None
    state: str | None = None
    action: str | None = None


class SpeechPlayer(QObject):
    """Turns complete or SSE replies into paced bubble fragments using Qt timers."""

    started = pyqtSignal()
    text_ready = pyqtSignal(str)
    segment_started = pyqtSignal(object)
    segment_finished = pyqtSignal(object)
    # Compatibility with the original ChatStreamer public signal.
    sentence_finished = pyqtSignal(str)
    finished = pyqtSignal()

    # Commas and colons create the small conversational beats; sentence endings
    # and ellipses create longer ones. Consecutive punctuation stays together.
    _BOUNDARY = re.compile(r"(?:\.{3,}|…{1,2}|[。！？!?；;：:,，]+)(?:[\"'”’）)】\]}]*)")

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
        self._queue: deque[SpeechSegment] = deque()
        self._buffer = ""
        self._current: SpeechSegment | None = None
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

    @classmethod
    def split_reply(
        cls, text: str, *, emotion: str | None = None,
        state: str | None = None, action: str | None = None,
    ) -> list[SpeechSegment]:
        segments: list[SpeechSegment] = []
        start = 0
        for match in cls._BOUNDARY.finditer(str(text)):
            end = match.end()
            value = str(text)[start:end]
            if value:
                punctuation = match.group(0)
                pause = 520 if re.search(r"…|\.{3,}|[。！？!?]", punctuation) else 240
                segments.append(SpeechSegment(value, pause, emotion, state, action))
            start = end
        tail = str(text)[start:]
        if tail:
            segments.append(SpeechSegment(tail, 260, emotion, state, action))
        return segments

    def start(self) -> None:
        self._timer.stop()
        self._queue.clear()
        self._buffer = ""
        self._current = None
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
        self._buffer += token
        self._extract_complete_segments()
        self._schedule_if_needed(initial=not self._has_output)

    def push_segments(self, segments: Iterable[SpeechSegment]) -> None:
        if not self._active:
            self.start()
        for segment in segments:
            if segment.text:
                self._received_text += segment.text
                self._queue.append(segment)
        self._schedule_if_needed(initial=not self._has_output)

    def finish(self) -> None:
        if not self._active:
            return
        if self._buffer:
            self._queue.append(SpeechSegment(self._buffer))
            self._buffer = ""
        self._producer_finished = True
        self._schedule_if_needed(initial=not self._has_output)
        self._finish_if_drained()

    def _extract_complete_segments(self) -> None:
        start = 0
        matches = list(self._BOUNDARY.finditer(self._buffer))
        for match in matches:
            end = match.end()
            text = self._buffer[start:end]
            punctuation = match.group(0)
            pause = 520 if re.search(r"…|\.{3,}|[。！？!?]", punctuation) else 240
            if text:
                self._queue.append(SpeechSegment(text, pause))
            start = end
        if start:
            self._buffer = self._buffer[start:]

    def _schedule_if_needed(self, *, initial: bool) -> None:
        if self._timer.isActive() or self._current is not None or not self._queue:
            return
        delay_range = self._initial_pause if initial else self._character_pause
        self._timer.start(self._randint(*delay_range))

    def _advance(self) -> None:
        if self._current is None:
            if not self._queue:
                self._finish_if_drained()
                return
            self._current = self._queue.popleft()
            self._offset = 0
            self.segment_started.emit(self._current)
        end = min(len(self._current.text), self._offset + self._characters_per_tick)
        fragment = self._current.text[self._offset:end]
        self._offset = end
        if fragment:
            self._has_output = True
            self.text_ready.emit(fragment)
        if self._offset >= len(self._current.text):
            completed = self._current
            self._current = None
            self._offset = 0
            self.segment_finished.emit(completed)
            self.sentence_finished.emit(completed.text)
            if self._queue:
                low, high = self._sentence_pause
                delay = max(low, min(high, completed.pause_after_ms))
                self._timer.start(delay)
            else:
                self._finish_if_drained()
        else:
            self._timer.start(self._randint(*self._character_pause))

    def _finish_if_drained(self) -> None:
        if self._active and self._producer_finished and not self._queue and self._current is None:
            self._active = False
            self.finished.emit()
