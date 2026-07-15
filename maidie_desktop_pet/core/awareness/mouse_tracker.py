"""维护最近鼠标位置、速度和活动时间的轻量快照。

``PetController`` 将已有鼠标事件喂给 Tracker，并由 ``IdleDetector`` 统一更新时间；
该模块不安装额外监听器，避免 Awareness 隐式扩大输入采集范围。
"""

from __future__ import annotations

from math import hypot
from time import monotonic
from typing import Callable

from core.awareness.idle_detector import IdleDetector


class MouseTracker:
    """Turns cursor samples into speed and active/idle semantic state."""

    def __init__(self, idle_detector: IdleDetector, slow_speed: float = 80.0,
                 fast_speed: float = 700.0, clock: Callable[[], float] = monotonic) -> None:
        self.idle_detector = idle_detector
        self.slow_speed, self.fast_speed = float(slow_speed), float(fast_speed)
        self._clock = clock
        self._last: tuple[float, float, float] | None = None
        self.speed = 0.0

    def record(self, x: float, y: float, at: float | None = None) -> None:
        now = self._clock() if at is None else float(at)
        if self._last:
            old_x, old_y, old_at = self._last
            elapsed = max(0.001, now - old_at)
            self.speed = hypot(x - old_x, y - old_y) / elapsed
        self._last = (float(x), float(y), now)
        self.idle_detector.mark_activity(now)

    @property
    def state(self) -> str:
        if self.idle_detector.state == "idle":
            return "idle"
        if self.speed >= self.fast_speed:
            return "fast_move"
        if self.speed > 0 and self.speed <= self.slow_speed:
            return "slow_move"
        return "active"
