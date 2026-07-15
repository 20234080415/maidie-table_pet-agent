"""为进行中的 AI 请求选择简短、非最终的等待反馈。

Session 在后台 Brain 开始工作后调用本模块，根据 Time、Weather、Vision 或技术请求
选择不同提示；这些文本只缓解等待感，不参与 Router 决策或最终 Synthesizer 输出。
"""

from __future__ import annotations

import random
import re
from typing import Callable

from core.brain.fast_route import is_simple_time_query, is_weather_query
from core.vision.intent_rules import is_cursor_region_request


class ThinkingFeedbackPool:
    """按请求类型选择简短且非最终的对话提示。

    默认实例贯穿 Session 生命周期；注入 ``chooser`` 可让测试控制随机选择。
    """

    SCREEN = ("让我看看。", "我瞧瞧屏幕。", "嗯，我看看这里。", "我先看一眼。")
    CURSOR = ("把鼠标移回要看的位置，三秒后我截图。",)
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
        if is_cursor_region_request(text):
            return self.CURSOR
        if self.SCREEN_QUERY.search(text):
            return self.SCREEN
        if is_simple_time_query(text) or is_weather_query(text):
            return self.LOOKUP
        if self.TECHNICAL_QUERY.search(text):
            return self.TECHNICAL
        return self.CHAT
