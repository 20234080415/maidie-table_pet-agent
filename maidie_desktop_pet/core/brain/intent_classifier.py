from __future__ import annotations

import re


class IntentClassifier:
    """Deterministic V4 intent gate. No language model participates."""

    SCREEN = re.compile(
        r"你能.*(?:看到|看见).*(?:屏幕|桌面)|我在(?:干嘛|做什么)|"
        r"你知道我在(?:干嘛|做什么|写代码)|你能监控我吗|"
        r"(?:屏幕|桌面).*(?:内容|有什么|是什么)|"
        r"\b(?:can you see my screen|what am i doing|monitor my screen)\b",
        re.I,
    )
    TASK = re.compile(
        r"天气|气温|温度|下雨|几点|时间|日期|星期|查资料|查一下|查询|搜索|"
        r"最新|新闻|适不适合|是否适合|适合.*吗|要不要|该不该|是否应该|建议|推荐|"
        r"\b(?:weather|temperature|time|date|search|look up|latest|should|recommend)\b",
        re.I,
    )

    def classify(self, user_input: str) -> str:
        text = str(user_input).strip()
        if self.SCREEN.search(text):
            return "screen"
        if self.TASK.search(text):
            return "task"
        return "chat"
