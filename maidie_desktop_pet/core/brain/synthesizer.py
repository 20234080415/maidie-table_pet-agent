from __future__ import annotations

import json
from typing import Any, Callable

from ai.client import normalize_response
from core.brain.fast_route import is_simple_time_query, is_simple_weather_query
from core.performance import mark
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
        if source == "clarification":
            mark(local_response_used=True)
            normalized = {"text": "你是想让我看屏幕吗？可以说‘看当前窗口’、‘看全屏’、‘看鼠标这块’，或者‘我框选一下’。",
                          "emotion": "thinking",
                          "action": "talk", "state": "talking", "source": source}
        elif source == "vision_cleared":
            mark(local_response_used=True)
            normalized = {"text": "好，我不再沿用刚才的屏幕内容了。", "emotion": "idle",
                          "action": "talk", "state": "talking", "source": source}
        elif plan and plan.get("missing_search_query"):
            mark(local_response_used=True)
            normalized = {"text": "主人想让我搜什么呀？", "emotion": "shy",
                          "action": "talk", "state": "talking", "source": source}
        elif any(item.get("tool") == "search" and not item.get("ok") for item in tool_data):
            mark(local_response_used=True)
            normalized = self._local_fallback(source, tool_data)
        elif self.should_use_local_tool_response(user_input, tool_data):
            mark(local_response_used=True)
            normalized = self._local_fallback(source, tool_data)
        elif source == "screen" and self._screen_failure(tool_data):
            normalized = self._local_fallback(source, tool_data)
        elif source != "chat" and not self._client_ready(client):
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
    def should_use_local_tool_response(user_input: str,
                                       tool_data: list[dict[str, Any]]) -> bool:
        successful_types = {
            str(item.get("data", {}).get("type", ""))
            for item in tool_data if item.get("ok")
        }
        return (("time" in successful_types and is_simple_time_query(user_input))
                or ("weather" in successful_types and is_simple_weather_query(user_input)))

    @staticmethod
    def _client_ready(client: Any) -> bool:
        return not hasattr(client, "api_key") or bool(
            client.api_key and client.api_key != "YOUR_API_KEY_HERE"
        )

    @staticmethod
    def _local_fallback(source: str, tool_data: list[dict[str, Any]]) -> dict[str, str]:
        successful = [item.get("data", {}) for item in tool_data if item.get("ok")]
        if not successful:
            failed_search = next((item.get("data", {}).get("raw", {}) for item in tool_data
                                  if item.get("tool") == "search"), {})
            failed_screen = next((item.get("data", {}).get("raw", {}) for item in tool_data
                                  if item.get("tool") == "screen"), {})
            reason = str(failed_search.get("failure_reason", ""))
            query = str(failed_search.get("query", ""))
            code = str(failed_screen.get("error_code", ""))
            detail = str(failed_screen.get("error", ""))
            if reason == "EMPTY_QUERY":
                text = "主人想让我搜什么呀？"
            elif reason == "API_KEY_MISSING":
                text = "搜索功能还没配置好，需要检查 Tavily API Key。"
            elif reason == "NETWORK_ERROR":
                text = "搜索工具好像连不上，我等会儿再试。"
            elif reason == "TIMEOUT":
                text = "搜索工具等太久啦，稍后我再试一次。"
            elif reason in {"EMPTY_RESULTS", "LOW_CONFIDENCE_RESULTS"}:
                text = f"我搜了“{query or '这个内容'}”，但没找到靠谱结果。"
            elif failed_search:
                text = "搜索时出了点意外，我已经把原因记进日志啦。"
            elif code == "ocr_disabled":
                text = "屏幕 OCR 当前未启用，所以我还读不到屏幕文字；请先在设置中开启屏幕理解。"
            elif code == "no_external_window":
                text = "当前前台是 Maidie 自己，且没有找到可读取的外部窗口，请先切回题目或报错窗口再试。"
            elif code == "vision_config_missing":
                text = "视觉能力还没配置好，需要先设置千问视觉 API Key。"
            elif code == "vision_capture_failed":
                text = "我现在没法获取屏幕截图，可能是权限或窗口状态的问题。"
            elif code == "vision_api_failed":
                text = "我刚刚看屏幕失败了，可能是网络或模型服务问题，可以稍后再试。"
            elif source == "screen":
                text = f"屏幕读取失败：{detail or '截图或 OCR 没有返回可用数据'}。"
            else:
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
                screen_text = str(raw.get("screen_text") or raw.get("screenshot_summary") or "").strip()
                text = (screen_text if screen_text else
                        f"当前外部窗口是 {raw.get('window') or raw.get('app', '未知窗口')}，"
                        f"场景为 {raw.get('context', 'unknown')}。")
            elif kind == "search":
                text = str(raw.get("summary") or raw.get("error") or "暂时没查到可靠资料。")
            else:
                text = "我已经记下相关情况啦。"
        return {"text": text, "emotion": "thinking", "action": "talk", "state": "talking",
                "source": source}

    @staticmethod
    def _screen_failure(tool_data: list[dict[str, Any]]) -> bool:
        return any(item.get("tool") == "screen" and not item.get("ok") for item in tool_data)

    def _prompt(self, user_input: str, source: str, plan: dict[str, Any] | None,
                tool_data: list[dict[str, Any]], memory_context: str) -> str:
        facts = json.dumps(tool_data, ensure_ascii=False, default=str)
        task = (
            "你是 Maidie 的推理与回答模块。视觉模型只负责观察，最终答案由你生成。"
            "不要假装看到视觉结构化结果未提供的内容；信息不足时说明不确定并建议下一步。"
            "代码报错要解释最可能原因并给修复建议；题目先讲思路再给答案；"
            "软件界面要给出具体下一步操作。回答具体、可执行，不过度卖萌。"
            "尽量自然地依次说明：看到了什么、问题原因或当前状态、现在可以怎么做、"
            "可复制的命令或代码，以及仍未解决时下一步该让我看哪里。不要机械输出固定标题。"
            if source == "screen" else
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
