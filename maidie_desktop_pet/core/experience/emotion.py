from __future__ import annotations

import math
from time import monotonic
from typing import Callable


class EmotionState:
    """Small decaying emotion vector, independent from Qt and animation names."""

    EMOTIONS = ("happy", "thinking", "shy", "concern", "failed")
    EVENT_DELTAS = {
        "ai_reply": {"happy": 0.22, "thinking": -0.15},
        "ai_thinking": {"thinking": 0.65},
        "tool_success": {"happy": 0.35, "failed": -0.25},
        "tool_failure": {"failed": 0.75, "concern": 0.35},
        "headpat": {"happy": 0.7, "shy": 0.25},
        "facepoke": {"shy": 0.6, "concern": 0.2},
    }

    def __init__(self, *, half_life_seconds: float = 90.0,
                 clock: Callable[[], float] = monotonic) -> None:
        self.half_life_seconds = max(0.001, float(half_life_seconds))
        self._clock = clock
        self._updated_at = clock()
        self._values = {name: 0.0 for name in self.EMOTIONS}

    def snapshot(self) -> dict[str, float]:
        self._decay()
        return dict(self._values)

    def add(self, emotion: str, amount: float) -> None:
        self._decay()
        name = self._normalize(emotion)
        if name in self._values:
            self._values[name] = max(0.0, min(1.0, self._values[name] + float(amount)))

    def apply_event(self, event: str, emotion: str | None = None) -> None:
        self._decay()
        for name, amount in self.EVENT_DELTAS.get(event, {}).items():
            self._values[name] = max(0.0, min(1.0, self._values[name] + amount))
        if emotion:
            self.add(emotion, 0.45)

    def get_dominant_emotion(self, default: str = "idle") -> str:
        values = self.snapshot()
        name = max(values, key=values.get)
        return name if values[name] >= 0.08 else default

    def _decay(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated_at)
        if elapsed:
            factor = math.pow(0.5, elapsed / self.half_life_seconds)
            self._values = {name: value * factor for name, value in self._values.items()}
            self._updated_at = now

    @staticmethod
    def _normalize(emotion: str) -> str:
        return {"sad": "concern", "excited": "happy", "speaking": "happy"}.get(emotion, emotion)
