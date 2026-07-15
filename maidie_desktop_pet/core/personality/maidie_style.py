"""在 Synthesizer 出口统一 Maidie 的语气和响应字段。

``MaidieStyle`` 从 ``core.prompts.personality`` 获取基线人格，并对本地模板与 LLM 结果
使用相同的文本保护和默认值，避免不同回答路径呈现不一致。
"""

from __future__ import annotations

import re
from typing import Any

from core.prompts.personality import MAIDIE_STYLE_PROMPT


class MaidieStyle:
    """The final, non-optional personality guard for every V4 response."""

    PROMPT = MAIDIE_STYLE_PROMPT
    MARKERS = ("哼", "好啦", "才不是", "嘛", "啦", "哦", "呢", "呀", "诶", "欸", "嘿嘿", "~", "～")
    INTERNAL_PATTERN = re.compile(
        r"(?:我|系统)?(?:调用|使用|执行|通过)(?:了)?\s*(?:the\s+)?(?:\w+\s*)?(?:tool|工具)|"
        r"Router|Planner|Synthesizer|pipeline|内部流程",
        re.IGNORECASE,
    )

    def prompt(self, extra: str = "") -> str:
        return self.PROMPT + (f"\n补充人格：{extra.strip()}" if extra.strip() else "")

    def preserve(self, text: str) -> str:
        value = str(text or "").strip() or "我在这里呢。"
        value = self.INTERNAL_PATTERN.sub("我稍微看了一下", value)
        if not any(marker in value for marker in self.MARKERS):
            value = f"好啦好啦，{value}"
        return value

    @staticmethod
    def normalize_fields(result: dict[str, Any], source: str) -> dict[str, str]:
        emotion = str(result.get("emotion", "idle"))
        action = str(result.get("action", "talk"))
        state = str(result.get("state", "talking"))
        return {
            "text": str(result.get("text", "")),
            "emotion": emotion if emotion in {"idle", "happy", "thinking", "shy"} else "idle",
            "action": action if action in {"talk", "react", "think"} else "talk",
            "state": state if state in {"talking", "idle", "thinking"} else "talking",
            "source": source,
        }
