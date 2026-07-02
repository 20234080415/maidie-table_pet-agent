from __future__ import annotations

import re
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable

from core.experience.attention import AttentionState


@dataclass(frozen=True)
class BehaviorDecision:
    kind: str
    reason: str
    action: str = "idle"
    priority: int = 20


class BehaviorOrchestrator:
    """Produces throttled local behavior candidates; it never invokes an LLM."""

    ERROR = re.compile(r"error|exception|traceback|failed|报错|错误", re.I)

    def __init__(self, *, cooldown_seconds: float = 900.0,
                 break_after_seconds: float = 7200.0,
                 clock: Callable[[], float] = monotonic) -> None:
        self.cooldown_seconds = max(30.0, float(cooldown_seconds))
        self.break_after_seconds = max(300.0, float(break_after_seconds))
        self._clock = clock
        self._last_decision = float("-inf")
        self._activity_since: dict[str, float] = {}

    def decide(self, attention: AttentionState, emotion: str, idle_time: float,
               active_window: str = "") -> BehaviorDecision | None:
        now = self._clock()
        if now - self._last_decision < self.cooldown_seconds:
            return None
        activity = attention.activity_type
        self._activity_since.setdefault(activity, now)
        self._activity_since = {activity: self._activity_since[activity]}
        window = active_window or attention.window_title
        decision: BehaviorDecision | None = None
        if self.ERROR.search(f"{window} {attention.screen_summary}") and attention.confidence >= 0.35:
            decision = BehaviorDecision("error_notice", "current view appears to contain an error", "concern")
        elif activity == "coding" and now - self._activity_since[activity] >= self.break_after_seconds:
            decision = BehaviorDecision("break_reminder", "long continuous coding session", "shy")
        elif activity == "coding" and emotion in {"thinking", "concern", "failed"}:
            decision = BehaviorDecision("coding_nudge", "coding context matches current mood", "thinking")
        elif activity == "gaming":
            decision = BehaviorDecision("game_tease", "active application is a game", "happy")
        elif idle_time >= 60:
            decision = BehaviorDecision("idle_glance", "user has been idle", "idle", 10)
        if decision:
            self._last_decision = now
        return decision
