from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

import requests

from ai.prompt import (
    CODEX_STREAM_PROMPT,
    CODEX_SYSTEM_PROMPT,
    MAIDIE_STREAM_PROMPT,
    MAIDIE_SYSTEM_PROMPT,
)


AIResponse = dict[str, str]


def normalize_response(result: dict[str, Any], source: str) -> AIResponse:
    default_state = "thinking" if result.get("action") == "thinking" else "talking"
    return {
        "text": str(result.get("text") or "Maidie is here."),
        "emotion": str(result.get("emotion") or "idle"),
        "action": str(result.get("action") or "talk"),
        "state": str(result.get("state") or default_state),
        "source": source,
    }


class AIClient(ABC):
    @abstractmethod
    def ask(self, prompt: str, context: list[dict[str, Any]]) -> AIResponse:
        raise NotImplementedError

    def ask_stream(
        self,
        prompt: str,
        context: list[dict[str, Any]],
        on_delta: Callable[[str], None],
    ) -> AIResponse:
        result = self.ask(prompt, context)
        on_delta(result["text"])
        return result


class OpenAICompatibleClient(AIClient):
    """Reusable OpenAI-compatible backend for chat or Codex-style reasoning."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        system_prompt: str = MAIDIE_SYSTEM_PROMPT,
        source: str = "chat",
        personality_prompt: str = "",
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.source = source
        self.personality_prompt = personality_prompt
        self.timeout = timeout

    @classmethod
    def clients_from_config(cls, path: Path) -> tuple["OpenAICompatibleClient", "OpenAICompatibleClient"]:
        config = json.loads(path.read_text(encoding="utf-8"))
        shared = config.get("ai", {})
        codex = config.get("codex", {})
        provider = shared.get("provider", "deepseek")
        environment_key = os.getenv("DEEPSEEK_API_KEY") if provider == "deepseek" else ""
        api_key = environment_key or shared.get("api_key", "")
        chat_client = cls(
            api_key=api_key,
            base_url=shared.get("base_url", "https://api.deepseek.com"),
            model=shared.get("model", "deepseek-v4-flash"),
            system_prompt=MAIDIE_SYSTEM_PROMPT,
            source="chat",
            personality_prompt=str(config.get("personality", {}).get("custom_prompt", "")),
            timeout=int(shared.get("timeout", 30)),
        )
        codex_client = cls(
            api_key=environment_key or codex.get("api_key") or api_key,
            base_url=codex.get("base_url") or shared.get("base_url", "https://api.deepseek.com"),
            model=codex.get("model", "deepseek-v4-pro"),
            system_prompt=CODEX_SYSTEM_PROMPT,
            source="codex",
            timeout=int(codex.get("timeout", 90)),
        )
        return chat_client, codex_client

    @classmethod
    def from_config(cls, path: Path) -> "OpenAICompatibleClient":
        return cls.clients_from_config(path)[0]

    def ask(self, prompt: str, context: list[dict[str, Any]]) -> AIResponse:
        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            if self.source == "codex":
                return normalize_response({
                    "text": "技术模式已经准备好啦，不过还没有配置 DeepSeek API Key。",
                    "emotion": "thinking", "action": "thinking", "state": "thinking",
                }, "codex")
            return normalize_response({
                "text": "主人终于想起我啦？哼，我才没有一直在等呢。",
                "emotion": "excited", "action": "talk", "state": "talking",
            }, "chat")

        system_prompt = self.system_prompt
        if self.source == "chat" and self.personality_prompt:
            system_prompt += f"\nCurrent personality: {self.personality_prompt}"
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for item in context[-10:]:
            messages.extend([
                {"role": "user", "content": str(item.get("message", ""))},
                {"role": "assistant", "content": str(item.get("response", ""))},
            ])
        messages.append({"role": "user", "content": prompt})
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.8 if self.source == "chat" else 0.2,
                "response_format": {"type": "json_object"},
                "max_tokens": 2048,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return normalize_response(json.loads(content), self.source)

    def ask_stream(
        self,
        prompt: str,
        context: list[dict[str, Any]],
        on_delta: Callable[[str], None],
    ) -> AIResponse:
        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            result = self.ask(prompt, context)
            on_delta(result["text"])
            return result

        streaming_prompt = (
            CODEX_STREAM_PROMPT if self.source == "codex" else MAIDIE_STREAM_PROMPT
        )
        if self.source == "chat" and self.personality_prompt:
            streaming_prompt += f"\nCurrent personality: {self.personality_prompt}"
        messages: list[dict[str, str]] = [{"role": "system", "content": streaming_prompt}]
        for item in context[-10:]:
            messages.extend([
                {"role": "user", "content": str(item.get("message", ""))},
                {"role": "assistant", "content": str(item.get("response", ""))},
            ])
        messages.append({"role": "user", "content": prompt})
        chunks: list[str] = []
        with requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.8 if self.source == "chat" else 0.2,
                "max_tokens": 2048,
                "stream": True,
            },
            timeout=self.timeout,
            stream=True,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                event = json.loads(payload)
                delta = event.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    chunks.append(delta)
                    on_delta(delta)
        text = "".join(chunks).strip()
        if not text:
            raise RuntimeError("DeepSeek returned an empty streaming response")
        return normalize_response({
            "text": text,
            "emotion": "thinking" if self.source == "codex" else "idle",
            "action": "talk",
            "state": "talking",
        }, self.source)

    def reconfigure(
        self,
        api_key: str,
        base_url: str,
        model: str,
        personality_prompt: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        if personality_prompt is not None:
            self.personality_prompt = personality_prompt
