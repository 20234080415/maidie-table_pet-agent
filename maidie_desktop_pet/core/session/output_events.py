"""定义 Brain/Tool 到 Session/UI 的稳定输出事件协议。

事件携带 request、generation 与 sequence，使异步消费者能拒绝旧请求或乱序数据；
``OutputMode`` 让 ChatStreamer 区分自然对话、任务流和 Tool 进度。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class OutputMode(str, Enum):
    """声明 UI 应采用的流式展示策略，而非回答内容类型。"""
    CHAT_NATURAL = "CHAT_NATURAL"
    TASK_STREAM = "TASK_STREAM"
    TASK_PROGRESS = "TASK_PROGRESS"


@dataclass(frozen=True)
class OutputEvent:
    """一次不可变的 Session 输出事件，可安全跨线程序列化传递。"""
    request_id: str
    generation: int
    sequence: int
    type: str
    mode: OutputMode
    content: str
    source: str = ""
    tool: str = ""
    phase: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        return payload

    @classmethod
    def from_payload(
        cls, payload: dict[str, Any], *, request_id: str,
        generation: int, sequence: int,
    ) -> "OutputEvent":
        """把 Brain/Tool payload 补全为当前 Session 身份下的严格事件。"""
        raw_mode = payload.get("mode", OutputMode.CHAT_NATURAL.value)
        try:
            mode = raw_mode if isinstance(raw_mode, OutputMode) else OutputMode(str(raw_mode))
        except ValueError:
            mode = OutputMode.CHAT_NATURAL
        return cls(
            request_id=request_id,
            generation=generation,
            sequence=sequence,
            type=str(payload.get("type") or "token"),
            mode=mode,
            content=str(payload.get("content") or ""),
            source=str(payload.get("source") or ""),
            tool=str(payload.get("tool") or ""),
            phase=str(payload.get("phase") or ""),
        )
