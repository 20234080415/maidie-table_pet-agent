from __future__ import annotations

import re
from typing import Any, Callable

from ai.client import AIClient, AIResponse, normalize_response


class AIRouter:
    """Routes technical intent to Codex and social intent to Maidie chat."""

    TECHNICAL_PATTERN = re.compile(
        r"\b(code|coding|error|exception|traceback|compile|compiler|ssh|linux|debug|"
        r"debugging|architecture|refactor|function|class|api|database|git|python|"
        r"javascript|typescript|docker|kubernetes|file|terminal)\b|"
        r"代码|报错|错误|编译|调试|架构|重构|函数|类|接口|数据库|文件|终端|服务器|部署",
        re.IGNORECASE,
    )

    def __init__(self, chat_client: AIClient, codex_client: AIClient):
        self.chat_client = chat_client
        self.codex_client = codex_client

    def classify(self, text: str) -> str:
        return "codex" if self.TECHNICAL_PATTERN.search(text) else "chat"

    def ask(self, prompt: str, context: list[dict[str, Any]]) -> AIResponse:
        source = self.classify(prompt)
        client = self.codex_client if source == "codex" else self.chat_client
        return normalize_response(client.ask(prompt, context), source)

    def ask_stream(
        self,
        prompt: str,
        context: list[dict[str, Any]],
        on_delta: Callable[[str], None],
    ) -> AIResponse:
        source = self.classify(prompt)
        client = self.codex_client if source == "codex" else self.chat_client
        return normalize_response(client.ask_stream(prompt, context, on_delta), source)
