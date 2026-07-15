"""增量识别流式文本中的句子边界。

ChatStreamer 将输出 chunk 喂入本类；未完成尾句保留在 buffer，完成或取消时显式
flush/reset，避免半句话提前进入气泡和语音节奏层。
"""

from __future__ import annotations


class SentenceSplitter:
    """Incrementally extracts complete sentences from streamed text."""

    TERMINATORS = frozenset("。！？.!?")

    def __init__(self) -> None:
        self._buffer = ""

    @property
    def buffer(self) -> str:
        return self._buffer

    def reset(self) -> None:
        self._buffer = ""

    def feed(self, token: str) -> list[str]:
        sentences: list[str] = []
        for character in token:
            self._buffer += character
            if character in self.TERMINATORS:
                sentences.append(self._buffer)
                self._buffer = ""
        return sentences

    def flush(self) -> str:
        remainder = self._buffer
        self._buffer = ""
        return remainder
