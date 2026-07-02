from __future__ import annotations

import random
import re
from typing import Callable

from core.brain.fast_route import is_simple_time_query, is_weather_query


class ThinkingFeedbackPool:
    """Chooses a brief, non-final conversational cue for an active request."""

    SCREEN = ("让我看看。", "我瞧瞧屏幕。", "嗯，我看看这里。", "我先看一眼。")
    LOOKUP = ("嗯，我查一下。", "让我看看现在的情况。", "我确认一下哦。", "稍等，我看看。")
    TECHNICAL = ("我想想。", "让我理一理。", "嗯，这个我琢磨一下。", "我先捋一捋思路。")
    CHAT = ("我想想。", "等我一下。", "让我想想怎么说。", "嗯……", "好呀，我想想。")
    SCREEN_QUERY = re.compile(r"屏幕|当前窗口|这个报错|这题|这个题|这里", re.I)
    TECHNICAL_QUERY = re.compile(r"代码|编译|linux|cmake|makefile|python|api|报错|bug", re.I)

    def __init__(self, chooser: Callable[[tuple[str, ...]], str] = random.choice) -> None:
        self._chooser = chooser

    def choose(self, message: str) -> str:
        return self._chooser(self.phrases_for(message))

    def phrases_for(self, message: str) -> tuple[str, ...]:
        text = str(message).strip()
        if self.SCREEN_QUERY.search(text):
            return self.SCREEN
        if is_simple_time_query(text) or is_weather_query(text):
            return self.LOOKUP
        if self.TECHNICAL_QUERY.search(text):
            return self.TECHNICAL
        return self.CHAT
