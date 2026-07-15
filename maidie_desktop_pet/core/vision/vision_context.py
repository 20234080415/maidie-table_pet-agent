"""定义 Vision provider 与 Brain 之间的结构化上下文契约。

``QwenVLClient`` 创建该对象，``VisionSession`` 短期保存，ProblemAnalyzer/ScreenTool 消费；
归一化集中在此，避免下游依赖 provider 原始 JSON 的缺失字段或异常类型。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VALID_TASK_TYPES = {
    "general_screen", "code_error", "math_problem", "document", "webpage",
    "image_question", "ui_operation", "unknown",
}


@dataclass
class VisionContext:
    """一次屏幕理解的标准化事实及置信度。

    对象可序列化跨越 Tool/Executor 边界；``raw_response`` 仅用于诊断兼容，不应作为
    Synthesizer 的主要事实来源。
    """
    screen_summary: str = ""
    visible_text: str = ""
    task_type: str = "unknown"
    important_regions: list[str] = field(default_factory=list)
    user_intent_guess: str = ""
    confidence: float = 0.0
    raw_response: str | None = None
    image_size: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        self.confidence = self._confidence(self.confidence)
        if self.task_type not in VALID_TASK_TYPES:
            self.task_type = "unknown"

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, raw_response: str | None = None,
                  image_size: tuple[int, int] | None = None) -> "VisionContext":
        regions = data.get("important_regions", [])
        return cls(
            screen_summary=str(data.get("screen_summary") or ""),
            visible_text=str(data.get("visible_text") or ""),
            task_type=str(data.get("task_type") or "unknown"),
            important_regions=[str(item) for item in regions] if isinstance(regions, list) else [],
            user_intent_guess=str(data.get("user_intent_guess") or ""),
            confidence=cls._confidence(data.get("confidence")),
            raw_response=raw_response,
            image_size=image_size,
        )

    @classmethod
    def fallback(cls, raw_response: str | None = None,
                 image_size: tuple[int, int] | None = None) -> "VisionContext":
        return cls(
            screen_summary="视觉结果无法完整解析，以下保留了模型返回的原始信息。",
            visible_text=str(raw_response or ""),
            task_type="unknown",
            important_regions=[],
            user_intent_guess="需要根据有限的屏幕信息回答用户",
            confidence=0.0,
            raw_response=raw_response,
            image_size=image_size,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
