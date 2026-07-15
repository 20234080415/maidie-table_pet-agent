"""提供兼容旧交互层的轻量情绪枚举与归一化。

新体验层的连续情绪状态位于 ``core.experience.emotion``；本模块保留离散枚举，供仍依赖
固定动画/状态名称的调用方使用，避免 UI 迁移时破坏公共接口。
"""

from enum import Enum


class Emotion(str, Enum):
    """旧交互接口使用的离散情绪标签。"""
    NEUTRAL = "idle"
    HAPPY = "happy"
    SAD = "sad"
    THINKING = "thinking"


class EmotionSystem:
    """Normalizes provider output without coupling it to the UI."""

    @staticmethod
    def normalize(value: str) -> Emotion:
        aliases = {"neutral": "idle", "talking": "idle", "excited": "happy"}
        try:
            return Emotion(aliases.get(str(value).lower(), str(value).lower()))
        except ValueError:
            return Emotion.NEUTRAL
