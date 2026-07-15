"""根据活动窗口与交互事件维护桌宠 Attention。

``AttentionManager`` 将环境输入压缩成稳定状态和可注入上下文，供 BehaviorOrchestrator
与 BrainPlanner 使用；它不直接改变动画或发起 AI 请求。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class AttentionState:
    """可安全传给行为与 Brain 层的不可变 Attention 快照。"""
    app_name: str = "unknown"
    window_title: str = ""
    activity_type: str = "unknown"
    screen_summary: str = ""
    confidence: float = 0.0
    updated_at: str = ""


class AttentionManager:
    """维护 Attention 快照及其更新节流策略。

    实例随 PetController 常驻，由 Awareness/交互事件更新；Brain 只读取精简结果，
    避免直接耦合窗口跟踪实现。
    """
    REFERENCES_CURRENT_VIEW = re.compile(
        r"(?:这个|这里|屏幕上|这题|这个报错|当前(?:页面|窗口|屏幕))|"
        r"\b(?:this|here|on (?:the|my) screen|this error)\b", re.I,
    )

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._state = AttentionState()
        self.clipboard_changed = False

    @property
    def state(self) -> AttentionState:
        return self._state

    def update(self, context: dict[str, Any]) -> AttentionState:
        screen = context.get("screen", {}) if isinstance(context.get("screen"), dict) else {}
        summary = str(screen.get("summary") or screen.get("screen_summary") or screen.get("screen_text") or "")
        summary = " ".join(summary.split())[:500]
        confidence = screen.get("confidence", context.get("confidence", 0.0))
        if not confidence and (context.get("active_app") or context.get("window_title")):
            confidence = 0.55
        self.clipboard_changed = bool(context.get("clipboard_changed", False))
        self._state = AttentionState(
            app_name=str(context.get("active_app") or context.get("app_name") or "unknown"),
            window_title=str(context.get("window_title") or context.get("window") or ""),
            activity_type=str(context.get("app_type") or context.get("window_state") or screen.get("context") or "unknown"),
            screen_summary=summary,
            confidence=max(0.0, min(1.0, float(confidence or 0.0))),
            updated_at=self._now().isoformat(),
        )
        return self._state

    def should_inject(self, user_input: str) -> bool:
        return bool(self.REFERENCES_CURRENT_VIEW.search(str(user_input)))

    def context_for(self, user_input: str) -> dict[str, Any] | None:
        if not self.should_inject(user_input):
            return None
        return {"attention": asdict(self._state)}
