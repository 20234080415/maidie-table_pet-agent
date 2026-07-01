from __future__ import annotations

import json
from typing import Any, Callable

from ai.client import normalize_response
from core.personality import MaidieStyle


class Synthesizer:
    """The only V4 layer allowed to turn facts into words for the user."""

    def __init__(self, chat_client: Any, codex_client: Any | None = None,
                 style: MaidieStyle | None = None, personality_prompt: str = "") -> None:
        self.chat_client = chat_client
        self.codex_client = codex_client or chat_client
        self.style = style or MaidieStyle()
        self.personality_prompt = personality_prompt

    def synthesize(self, user_input: str, source: str, plan: dict[str, Any] | None,
                   tool_data: list[dict[str, Any]], memory_context: str,
                   context: list[dict[str, Any]], on_delta: Callable[[str], None] | None = None,
                   technical: bool = False) -> dict[str, str]:
        client = self.codex_client if technical else self.chat_client
        prompt = self._prompt(user_input, source, plan, tool_data, memory_context)
        if source != "chat" and not self._client_ready(client):
            normalized = self._local_fallback(source, tool_data)
        else:
            try:
                # Buffer structured synthesis so JSON metadata never leaks into the bubble.
                response = (client.ask_stream(prompt, context, lambda _chunk: None)
                            if on_delta else client.ask(prompt, context))
                normalized = normalize_response(response, source)
            except Exception:
                normalized = {"text": "这次没拿到可靠结果，稍后再试试嘛。",
                              "emotion": "thinking", "action": "talk", "state": "talking"}
        normalized["text"] = self.style.preserve(normalized.get("text", ""))
        result = self.style.normalize_fields(normalized, source)
        if on_delta:
            on_delta(result["text"])
        return result

    @staticmethod
    def _client_ready(client: Any) -> bool:
        return not hasattr(client, "api_key") or bool(
            client.api_key and client.api_key != "YOUR_API_KEY_HERE"
        )

    @staticmethod
    def _local_fallback(source: str, tool_data: list[dict[str, Any]]) -> dict[str, str]:
        successful = [item.get("data", {}) for item in tool_data if item.get("ok")]
        if not successful:
            text = "这次没拿到可靠结果，稍后再试试嘛。"
        else:
            data = successful[0]
            raw = data.get("raw", {}) if isinstance(data, dict) else {}
            kind = data.get("type") if isinstance(data, dict) else ""
            if kind == "time" and raw.get("iso"):
                text = f"现在是 {str(raw['iso'])[11:16]} 哦。"
            elif kind == "weather":
                text = f"{raw.get('city', '')}气温 {raw.get('temperature', '未知')}，天气 {raw.get('forecast', '未知')}。"
            elif kind == "screen":
                text = (f"你正在 {raw.get('app', '当前应用')} 里，"
                        f"看起来是在{raw.get('context', '处理事情')}呢。")
            elif kind == "search":
                text = str(raw.get("summary") or raw.get("error") or "暂时没查到可靠资料。")
            else:
                text = "我已经记下相关情况啦。"
        return {"text": text, "emotion": "thinking", "action": "talk", "state": "talking",
                "source": source}

    def _prompt(self, user_input: str, source: str, plan: dict[str, Any] | None,
                tool_data: list[dict[str, Any]], memory_context: str) -> str:
        facts = json.dumps(tool_data, ensure_ascii=False, default=str)
        task = (
            "只依据下方工具数据回答，不得补全或猜测事实；数据报错或不足就可爱地说暂时没查到。"
            if source != "chat" else "这是纯桌宠聊天，不得声称读取了任何设备或外部事实。"
        )
        return (
            f"{self.style.prompt(self.personality_prompt)}\n{task}\n"
            "你是唯一输出层。隐藏所有内部步骤，只返回 JSON，字段严格为 text、emotion、action、state。"
            "emotion 仅限 idle|happy|thinking|shy；action 仅限 talk|react|think；"
            "state 仅限 talking|idle|thinking。\n"
            f"用户：{user_input}\n计划：{json.dumps(plan or {}, ensure_ascii=False)}\n"
            f"工具数据：{facts}\n记忆：{memory_context or '无'}"
        )
