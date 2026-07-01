from enum import Enum


class Emotion(str, Enum):
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
