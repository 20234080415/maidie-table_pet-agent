"""根据桌宠状态生成自主移动与待机行为意图。

``AutonomousBehaviorController`` 返回声明式决策，实际位移仍由 ``MovementController``
和 ``PetController`` 执行，从而隔离行为策略与物理更新。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from time import monotonic

from core.movement import Bounds, Vec2


class BehaviorKind(str, Enum):
    """自主行为策略可选择的有限行为集合。"""
    WANDER = "wander"
    IDLE_PAUSE = "idle_pause"
    CURIOUS = "curious"
    SLEEPY = "sleepy"


@dataclass(frozen=True)
class BehaviorIntent:
    """行为层提交给控制器的一次不可变决策。"""
    kind: BehaviorKind
    target: Vec2 | None = None
    run: bool = False


class AutonomousBehaviorController:
    """Plans infrequent purposeful actions instead of frame-by-frame jitter."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._next_decision = monotonic() + 2.0
        self.enabled = True
        self.curiosity_enabled = True

    def postpone(self, seconds: float) -> None:
        self._next_decision = monotonic() + seconds

    def decide(
        self,
        bounds: Bounds,
        window_size: tuple[float, float],
        cursor: Vec2 | None,
    ) -> BehaviorIntent | None:
        now = monotonic()
        if not self.enabled or now < self._next_decision:
            return None

        self._next_decision = now + self._rng.uniform(4.5, 9.0)
        width, height = window_size
        max_x = max(bounds.left, bounds.right - width)
        max_y = max(bounds.top, bounds.bottom - height)
        roll = self._rng.random()

        if self.curiosity_enabled and cursor and roll < 0.20:
            target = Vec2(
                max(bounds.left, min(max_x, cursor.x - width * 0.5)),
                max(bounds.top, min(max_y, cursor.y - height * 0.65)),
            )
            return BehaviorIntent(BehaviorKind.CURIOUS, target, False)
        if roll < 0.32:
            self._next_decision = now + self._rng.uniform(5.0, 9.0)
            return BehaviorIntent(BehaviorKind.SLEEPY)
        if roll < 0.50:
            self._next_decision = now + self._rng.uniform(1.8, 4.0)
            return BehaviorIntent(BehaviorKind.IDLE_PAUSE)

        margin = 24.0
        target = Vec2(
            self._rng.uniform(bounds.left + margin, max(bounds.left + margin, max_x - margin)),
            self._rng.uniform(bounds.top + margin, max(bounds.top + margin, max_y - margin)),
        )
        return BehaviorIntent(BehaviorKind.WANDER, target, self._rng.random() < 0.18)
