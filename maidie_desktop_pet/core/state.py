from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from time import monotonic


class PetState(str, Enum):
    IDLE = "idle"
    WALK = "walk"
    RUN = "run"
    TALKING = "talking"
    THINKING = "thinking"
    REACTING = "reacting"
    SLEEPING = "sleeping"


class BehaviorPriority(IntEnum):
    IDLE = 0
    AUTONOMOUS = 20
    AI_TALKING = 60
    CURSOR_INTERACTION = 80
    USER_CLICK = 100


@dataclass(frozen=True)
class StateSnapshot:
    state: PetState
    priority: BehaviorPriority
    changed_at: float
    locked_until: float


class StateMachine:
    """Framework-neutral state store. Only PetController owns an instance."""

    def __init__(self) -> None:
        now = monotonic()
        self._snapshot = StateSnapshot(PetState.IDLE, BehaviorPriority.IDLE, now, now)

    @property
    def snapshot(self) -> StateSnapshot:
        return self._snapshot

    @property
    def state(self) -> PetState:
        return self._snapshot.state

    def transition(
        self,
        state: PetState,
        priority: BehaviorPriority,
        lock_ms: int = 0,
        force: bool = False,
    ) -> bool:
        now = monotonic()
        current = self._snapshot
        if not force and now < current.locked_until and priority <= current.priority:
            return False
        if state == current.state and priority == current.priority:
            return False
        self._snapshot = StateSnapshot(
            state=state,
            priority=priority,
            changed_at=now,
            locked_until=now + max(0, lock_ms) / 1000,
        )
        return True

    def can_interrupt(self, priority: BehaviorPriority) -> bool:
        current = self._snapshot
        return monotonic() >= current.locked_until or priority > current.priority
