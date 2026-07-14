from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class OutputMode(str, Enum):
    CHAT_NATURAL = "CHAT_NATURAL"
    TASK_STREAM = "TASK_STREAM"
    TASK_PROGRESS = "TASK_PROGRESS"


@dataclass(frozen=True)
class OutputEvent:
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
