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
    DESKTOP_AGENT_CAPABILITY_PROMPT,
)
from core.prompts.memory import MEMORY_EXTRACTION_SYSTEM_PROMPT, build_memory_extraction_prompt


AIResponse = dict[str, str]


def normalize_response(result: dict[str, Any], source: str) -> AIResponse:
    result = _unwrap_nested_response(result)
    default_state = "thinking" if result.get("action") == "thinking" else "talking"
    return {
        "text": str(result.get("text") or "Maidie is here."),
        "emotion": str(result.get("emotion") or "idle"),
        "action": str(result.get("action") or "talk"),
        "state": str(result.get("state") or default_state),
        "source": source,
    }


def _unwrap_nested_response(result: dict[str, Any]) -> dict[str, Any]:
    """Recover when a model puts its JSON object inside the text field."""
    value = result.get("text")
    if not isinstance(value, str):
        return result
    candidate = value.strip()
    if candidate.startswith("```json") and candidate.endswith("```"):
        candidate = candidate[7:-3].strip()
    elif candidate.startswith("```") and candidate.endswith("```"):
        candidate = candidate[3:-3].strip()
    if not (candidate.startswith("{") and candidate.endswith("}")):
        return result
    try:
        nested = json.loads(candidate)
    except (TypeError, ValueError):
        return result
    if not isinstance(nested, dict) or not isinstance(nested.get("text"), str):
        return result
    merged = dict(result)
    merged.update({key: nested[key] for key in ("text", "emotion", "action", "state") if key in nested})
    return merged


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

    def extract_memories(self, message: str, response: str) -> dict[str, list[Any]]:
        return {"facts": [], "preferences": []}

    def plan_task(self, message: str, memory_context: str) -> dict[str, Any] | None:
        return None

    def route_intent(self, prompt: str, context: list[dict[str, Any]]) -> dict[str, Any]:
        result = self.ask(prompt, context)
        try:
            return json.loads(str(result.get("text", "")))
        except (TypeError, ValueError):
            return result

    def decide_recovery(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Use the client's strict-JSON path for one bounded recovery choice."""
        from core.prompts.recovery import build_recovery_prompt

        return self.route_intent(build_recovery_prompt(payload), [])


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
            if item.get("memory"):
                messages.append({"role": "system", "content": str(item["memory"])})
                continue
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
            if item.get("memory"):
                messages.append({"role": "system", "content": str(item["memory"])})
                continue
            messages.extend([
                {"role": "user", "content": str(item.get("message", ""))},
                {"role": "assistant", "content": str(item.get("response", ""))},
            ])
        messages.append({"role": "user", "content": prompt})
        chunks: list[str] = []
        request_body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.8 if self.source == "chat" else 0.2,
            "max_tokens": 2048,
            "stream": True,
            # V4 chat models otherwise may spend the entire token budget in
            # reasoning_content and never produce visible content.
            **({"thinking": {"type": "disabled"}} if self.source == "chat" else {}),
        }
        for attempt in range(2):
            try:
                with requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
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
                break
            except requests.ConnectionError:
                # A reset before the first visible delta is safe to replay.
                # Never retry after output started, which would duplicate text.
                if chunks or attempt == 1:
                    raise
        text = "".join(chunks).strip()
        if not text:
            raise RuntimeError("DeepSeek returned an empty streaming response")
        return normalize_response({
            "text": text,
            "emotion": "thinking" if self.source == "codex" else "idle",
            "action": "talk",
            "state": "talking",
        }, self.source)

    def route_intent(self, prompt: str, context: list[dict[str, Any]]) -> dict[str, Any]:
        """Ask the model for router JSON without Maidie response normalization."""
        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            raise RuntimeError("intent routing requires a configured LLM")
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "You return only strict JSON for intent routing."}
        ]
        for item in context[-6:]:
            if item.get("memory"):
                messages.append({"role": "system", "content": str(item["memory"])})
                continue
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
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "max_tokens": 300,
            },
            timeout=min(self.timeout, 20),
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("intent router returned non-object JSON")
        return result

    def extract_memories(self, message: str, response: str) -> dict[str, list[Any]]:
        """Extract durable, non-sensitive user memories from one exchange."""
        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            return {"facts": [], "preferences": []}
        prompt = build_memory_extraction_prompt(message, response)
        try:
            api_response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": DESKTOP_AGENT_CAPABILITY_PROMPT + "\n" + MEMORY_EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 800,
                },
                timeout=self.timeout,
            )
            api_response.raise_for_status()
            content = api_response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
            return {
                "facts": result.get("facts", []) if isinstance(result, dict) else [],
                "preferences": result.get("preferences", []) if isinstance(result, dict) else [],
            }
        except Exception:
            return {"facts": [], "preferences": []}

    def plan_task(self, message: str, memory_context: str) -> dict[str, Any] | None:
        """Ask the configured model for a strict tool plan; never answer the task here."""
        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            return None
        planner_prompt = (
            "你是 Maidie 的任务规划器，只能输出 JSON，不能回答用户。"
            "格式：{\"goal\":\"...\",\"steps\":[{\"tool\":"
            "\"time|weather|search|system|memory|llm\",\"action\":\"...\","
            "\"params\":{},\"requires_confirmation\":false}]}。至少一个步骤；显式选择工具；llm 只能用于最终总结。"
            "时间必须用 time，天气必须用 weather，需要外部资料才用 search。\n"
            "文件或应用操作必须用 system，并在 params.operation 指定动作；非只读操作 requires_confirmation 必须为 true。\n"
            f"用户背景：{memory_context or '无'}\n用户任务：{message}"
        )
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": DESKTOP_AGENT_CAPABILITY_PROMPT + "\n只生成任务计划 JSON。"},
                        {"role": "user", "content": planner_prompt},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 1000,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
            return result if isinstance(result, dict) else None
        except Exception:
            return None

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
