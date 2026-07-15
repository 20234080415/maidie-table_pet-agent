"""保存最近一次结构化 VisionContext，支持短时追问复用。

BrainRouter 用 Session 识别“那怎么修”等省略式追问；这里只保留最新结构化结果、问题和
回答元数据，不保留原始截图，并通过 TTL 防止陈旧画面长期影响对话。
"""

from __future__ import annotations

from time import monotonic
from typing import Callable

from core.vision.vision_context import VisionContext


class VisionSession:
    """保存最近结构化视觉上下文的短期会话对象。

    实例由 VisionService 持有并随应用运行，``clear`` 在用户显式清除或对话重置时调用；
    ``has_active_session`` 仅判断复用资格，不触发新截图。
    """

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self.last_context: VisionContext | None = None
        self.last_user_question: str | None = None
        self.last_answer: str | None = None
        self.created_at: float = 0.0
        self.updated_at: float = 0.0
        self.scope: str = "active_window"
        self.task_type: str | None = None
        self.confidence: float | None = None

    def has_active_session(self, ttl_seconds: int = 120) -> bool:
        if self.last_context is None:
            return False
        return self._clock() - self.updated_at <= max(0, ttl_seconds)

    def get_context(self) -> VisionContext | None:
        return self.last_context

    def age(self) -> float | None:
        if self.last_context is None:
            return None
        return max(0.0, self._clock() - self.updated_at)

    def update(self, context: VisionContext, user_question: str,
               answer: str | None = None, scope: str = "active_window") -> None:
        now = self._clock()
        if self.last_context is None:
            self.created_at = now
        self.last_context = context
        self.last_user_question = str(user_question)
        self.last_answer = answer
        self.updated_at = now
        self.scope = scope
        self.task_type = context.task_type
        self.confidence = context.confidence

    def clear(self) -> None:
        self.last_context = None
        self.last_user_question = None
        self.last_answer = None
        self.created_at = 0.0
        self.updated_at = 0.0
        self.scope = "active_window"
        self.task_type = None
        self.confidence = None
