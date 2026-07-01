from __future__ import annotations

from time import monotonic
from typing import Callable


class IdleDetector:
    """Tracks inactivity without platform hooks; activity is fed by input observers."""

    def __init__(self, idle_threshold: float = 60.0, clock: Callable[[], float] = monotonic) -> None:
        self.idle_threshold = max(1.0, float(idle_threshold))
        self._clock = clock
        self._last_activity = clock()

    def mark_activity(self, at: float | None = None) -> None:
        self._last_activity = self._clock() if at is None else float(at)

    @property
    def idle_time(self) -> float:
        return max(0.0, self._clock() - self._last_activity)

    @property
    def state(self) -> str:
        return "idle" if self.idle_time >= self.idle_threshold else "active"
