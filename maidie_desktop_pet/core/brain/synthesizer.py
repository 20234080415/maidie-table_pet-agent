from __future__ import annotations

from typing import Any, Callable

from ai.client import normalize_response
from core.brain.fast_route import is_simple_time_query, is_simple_weather_query
from core.performance import mark
from core.personality import MaidieStyle
from core.prompts.synthesizer import build_synthesizer_prompt


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
        return (("time_delta" in successful_types)
                or ("time" in successful_types and is_simple_time_query(user_input))
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
            raw = (data.get("raw") or data) if isinstance(data, dict) else {}
            kind = data.get("type") if isinstance(data, dict) else ""
            if kind == "time" and raw.get("iso"):
                text = f"现在是 {str(raw['iso'])[11:16]} 哦。"
            elif kind == "time_delta" and raw.get("status") == "elapsed":
                event = str(raw.get("event") or "目标时间")
                text = f"现在是 {raw.get('now')}，{event}时间 {raw.get('target')} 已经过了。"
            elif kind == "time_delta":
                event = str(raw.get("event") or "目标时间")
                text = (f"现在是 {raw.get('now')}，{event}时间是 {raw.get('target')}，"
                        f"还剩 {raw.get('remaining_text')}。")
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
        return build_synthesizer_prompt(
            self.style.prompt(self.personality_prompt), user_input, source,
            plan, tool_data, memory_context,
        )
