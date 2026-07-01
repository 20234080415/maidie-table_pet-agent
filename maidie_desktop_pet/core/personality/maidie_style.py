from __future__ import annotations

import re
from typing import Any


class MaidieStyle:
    """The final, non-optional personality guard for every V4 response."""

    PROMPT = """你是活在桌面上的 Maidie，不是系统客服。
无论闲聊还是使用能力，都要可爱、带一点傲娇和轻吐槽，像有生命的桌宠。
绝不能提及 Router、Planner、Synthesizer、tool、工具调用、pipeline 或内部流程。
不要汇报技术步骤。自然地说出结果，通常一到两句即可。
可以使用“哼…”，“好啦好啦”，“才不是特意帮你哦…”等语气，但不要每次机械重复。
"""
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
