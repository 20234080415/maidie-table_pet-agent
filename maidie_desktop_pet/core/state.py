"""定义桌宠交互状态机及行为抢占优先级。

Movement、Experience 与 ``PetController`` 通过 ``StateMachine`` 协调状态转换；集中式
``can_interrupt`` 规则避免动画、拖拽、对话等子系统各自修改状态而产生竞态。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from time import monotonic


class PetState(str, Enum):
    """桌宠运行期可见行为状态的有限集合。"""
    IDLE = "idle"
    WALK = "walk"
    RUN = "run"
    TALKING = "talking"
    THINKING = "thinking"
    REACTING = "reacting"
    SLEEPING = "sleeping"
    WATCHING = "watching"
    REMINDING = "reminding"


class BehaviorPriority(IntEnum):
    """决定新行为能否抢占当前状态的统一优先级。"""
    IDLE = 0
    AUTONOMOUS = 20
    PROACTIVE = 50
    AI_TALKING = 60
    CURSOR_INTERACTION = 80
    USER_CLICK = 100


@dataclass(frozen=True)
class StateSnapshot:
    """供 UI/控制器读取的不可变状态机快照。"""
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
        """按锁定窗口和优先级尝试转换状态，成功时返回 ``True``。

        ``force`` 仅供上层明确生命周期动作使用；一般行为必须服从统一抢占规则，避免
        拖拽、对话和自主移动相互覆盖。
        """
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
