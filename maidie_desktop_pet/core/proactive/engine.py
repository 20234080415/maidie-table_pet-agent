from __future__ import annotations

from dataclasses import dataclass
from random import random
from time import monotonic
from typing import Any, Callable


@dataclass(frozen=True)
class ProactiveDecision:
    kind: str
    prompt: str
    action: str = "happy"
    tools: tuple[str, ...] = ()


class ProactiveEngine:
    """Observes first, then emits a throttled intent for the normal Agent pipeline."""

    def __init__(self, enabled: bool = False, cooldown_seconds: float = 900.0,
                 idle_trigger_seconds: float = 300.0, coding_trigger_seconds: float = 7200.0,
                 random_chance: float = 0.05, clock: Callable[[], float] = monotonic,
                 random_fn: Callable[[], float] = random) -> None:
        self.enabled = enabled
        self.cooldown_seconds = max(30.0, cooldown_seconds)
        self.idle_trigger_seconds = idle_trigger_seconds
        self.coding_trigger_seconds = coding_trigger_seconds
        self.random_chance = max(0.0, min(1.0, random_chance))
        self._clock, self._random = clock, random_fn
        self._last_triggered = float("-inf")
        self._coding_since: float | None = None

    def should_trigger(self, context: dict[str, Any]) -> bool:
        now = self._clock()
        if not self.enabled or now - self._last_triggered < self.cooldown_seconds:
            return False
        if context.get("window_state") == "coding":
            self._coding_since = self._coding_since or now
        else:
            self._coding_since = None
        long_coding = self._coding_since is not None and now - self._coding_since >= self.coding_trigger_seconds
        return float(context.get("idle_time", 0)) >= self.idle_trigger_seconds or long_coding or self._random() < self.random_chance

    def decide(self, context: dict[str, Any], memory: Any = None) -> ProactiveDecision | None:
        if not self.should_trigger(context):
            return None
        self._last_triggered = self._clock()
        idle_time = float(context.get("idle_time", 0))
        if idle_time >= self.idle_trigger_seconds:
            return ProactiveDecision("care", "用户已经较长时间没有操作电脑。请温和提醒休息或活动一下，不要声称用户一定疲劳。", "sleepy", ("time",))
        if context.get("window_state") == "coding":
            return ProactiveDecision("care", "用户持续进行编程工作。请给一句简短、不打断思路的休息提醒。", "shy", ("time",))
        return ProactiveDecision("emotion", "结合当前上下文给一句简短陪伴，不要推测用户情绪或事实。", "shy")

    def mark_triggered(self) -> None:
        self._last_triggered = self._clock()
