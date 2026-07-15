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

    默认实例贯穿 Session 生命周期，并记录每类语境最近使用的短句，避免连续两次反馈
    完全相同；注入 ``chooser`` 可让测试控制随机选择。
    """

    SCREEN = (
        "让我看看...", "我瞧瞧屏幕...", "嗯，我看看这里...", "我先看一眼...",
        "好啦，我来看看...", "让我仔细瞧瞧...", "我看看画面里有什么...", "稍等，我观察一下...",
    )
    CURSOR = (
        "把鼠标移回要看的位置，三秒后我截图...",
        "鼠标先别动哦，三秒后我看那里...",
        "我准备看鼠标指着的位置了，给我三秒...",
        "好啦，把光标放到目标上，三秒后截图...",
    )
    SEARCH = (
        "好啦，我搜索一下...", "我去查查看...", "让我搜一下相关信息...", "稍等，我找找看...",
        "我来检索一下...", "嗯，我查查最新情况...", "交给我，我去搜搜...", "我先找找可靠的信息...",
    )
    TIME = (
        "我看看现在的时间...", "稍等，我确认一下时间...", "让我看一眼钟...", "好啦，我查下时间...",
        "我确认一下现在几点...", "等我看看日期和时间...",
    )
    WEATHER = (
        "我看看天气情况...", "稍等，我查下天气...", "让我看看外面的天气...", "好啦，我确认一下预报...",
        "我去看看今天的天气...", "嗯，我查查气温和天气...",
    )
    CODING = (
        "我看看这段代码...", "让我梳理一下实现...", "我先检查一下项目结构...", "好啦，我分析一下代码...",
        "我看看测试和调用链...", "让我定位一下相关文件...", "我先捋一捋修改思路...", "嗯，我检查一下实现细节...",
    )
    TECHNICAL = (
        "我想想...", "让我理一理...", "嗯，这个我琢磨一下...", "我先捋一捋思路...",
        "让我分析一下原因...", "我来排查一下...", "稍等，我看看问题出在哪...", "好啦，我检查一下细节...",
    )
    MEMORY = (
        "让我回想一下...", "我看看之前的记录...", "稍等，我翻翻记忆...", "嗯，我确认一下我们之前说过的...",
        "让我找找相关记忆...", "好啦，我回忆一下...",
    )
    CHAT = (
        "我想想...", "等我一下...", "让我想想怎么说...", "嗯，我琢磨一下...",
        "好呀，我想想...", "让我组织一下语言...", "稍等，我认真想想...", "唔，让我考虑一下...",
    )
    SCREEN_QUERY = re.compile(r"屏幕|截图|当前窗口|画面|鼠标.{0,4}(?:位置|附近|指着)|这(?:里|一块)", re.I)
    SEARCH_QUERY = re.compile(r"搜索|搜一下|搜搜|查一下|查询|检索|最新|新闻|资料", re.I)
    CODING_QUERY = re.compile(r"代码|项目|仓库|文件|函数|类|测试|重构|实现|patch|git|python|api", re.I)
    TECHNICAL_QUERY = re.compile(r"编译|linux|cmake|makefile|报错|异常|错误|bug|崩溃|日志|堆栈|配置", re.I)
    MEMORY_QUERY = re.compile(r"记得|记住|忘记|之前|上次|以前|我们说过|记录", re.I)

    def __init__(self, chooser: Callable[[tuple[str, ...]], str] = random.choice) -> None:
        self._chooser = chooser
        self._last: dict[tuple[str, ...], str] = {}

    def choose(self, message: str) -> str:
        phrases = self.phrases_for(message)
        previous = self._last.get(phrases)
        candidates = tuple(phrase for phrase in phrases if phrase != previous)
        selected = self._chooser(candidates or phrases)
        self._last[phrases] = selected
        return selected

    def phrases_for(self, message: str) -> tuple[str, ...]:
        text = str(message).strip()
        if is_cursor_region_request(text):
            return self.CURSOR
        if self.SCREEN_QUERY.search(text):
            return self.SCREEN
        if is_simple_time_query(text):
            return self.TIME
        if is_weather_query(text):
            return self.WEATHER
        if self.SEARCH_QUERY.search(text):
            return self.SEARCH
        if self.MEMORY_QUERY.search(text):
            return self.MEMORY
        if self.TECHNICAL_QUERY.search(text):
            return self.TECHNICAL
        if self.CODING_QUERY.search(text):
            return self.CODING
        return self.CHAT
