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

    def __init__(
        self,
        chat_client: AIClient,
        codex_client: AIClient,
        network_plugin: Any | None = None,
        tool_registry: Any | None = None,
    ):
        self.chat_client = chat_client
        self.codex_client = codex_client
        self.network_plugin = network_plugin
        self.tool_registry = tool_registry

    def classify(self, text: str) -> str:
        if self.tool_registry and self.tool_registry.match(text):
            return "tool"
        if self.network_plugin and self.network_plugin.should_handle(text):
            return "search"
        return "codex" if self.TECHNICAL_PATTERN.search(text) else "chat"

    def extract_memories(self, message: str, response: str) -> dict[str, list[Any]]:
        try:
            return self.chat_client.extract_memories(message, response)
        except Exception:
            return {"facts": [], "preferences": []}

    @staticmethod
    def _tool_response(result: dict[str, Any]) -> AIResponse:
        return normalize_response({
            "text": result.get("text", "工具已经处理完成。"),
            "emotion": "idle",
            "action": "talk",
            "state": "talking",
        }, "tool")

    def _run_tool(self, prompt: str) -> tuple[AIResponse | None, str | None]:
        if not self.tool_registry:
            return None, None
        tool = self.tool_registry.match(prompt)
        if tool is None:
            return None, None
        result = self.tool_registry.run(prompt)
        if result and not result.get("raw", {}).get("error"):
            return self._tool_response(result), tool.name
        return None, tool.name

    def _network_prompt(self, prompt: str) -> tuple[str, dict[str, Any] | None]:
        if not self.network_plugin or not self.network_plugin.should_handle(prompt):
            return prompt, None
        result = self.network_plugin.handle(prompt)
        if not result.get("ok"):
            return prompt, result
        sources = result.get("sources", [])
        source_text = "\n".join(
            f"- {item.get('title', '网页')}: {item.get('url', '')}"
            for item in sources
        )
        enriched = (
            f"用户当前问题：{prompt}\n\n"
            "以下是刚刚联网取得的资料。请仅将它作为当前回答的参考，不要把它写入长期记忆；"
            "不确定处要明确说明，不要编造。\n"
            f"摘要：{result.get('summary', '')}\n"
        )
        if self.network_plugin.show_sources and source_text:
            enriched += f"来源：\n{source_text}\n请在回答末尾简短列出来源。"
        return enriched, result

    def ask(self, prompt: str, context: list[dict[str, Any]]) -> AIResponse:
        tool_response, matched_tool = self._run_tool(prompt)
        if tool_response:
            return tool_response
        source = self.classify(prompt)
        network_result = None
        if matched_tool != "time":
            prompt, network_result = self._network_prompt(prompt)
        if network_result is not None and not network_result.get("ok"):
            return normalize_response({
                "text": f"呜，{network_result.get('error', '联网查询失败了')} 我们稍后再试一次吧。",
                "emotion": "sad", "action": "talk", "state": "talking",
            }, "search")
        client = self.codex_client if source == "codex" else self.chat_client
        fallback_source = "chat" if source in ("tool", "search") else source
        return normalize_response(
            client.ask(prompt, context), "search" if network_result else fallback_source
        )

    def ask_stream(
        self,
        prompt: str,
        context: list[dict[str, Any]],
        on_delta: Callable[[str], None],
    ) -> AIResponse:
        tool_response, matched_tool = self._run_tool(prompt)
        if tool_response:
            on_delta(tool_response["text"])
            return tool_response
        source = self.classify(prompt)
        network_result = None
        if matched_tool != "time":
            prompt, network_result = self._network_prompt(prompt)
        if network_result is not None and not network_result.get("ok"):
            result = normalize_response({
                "text": f"呜，{network_result.get('error', '联网查询失败了')} 我们稍后再试一次吧。",
                "emotion": "sad", "action": "talk", "state": "talking",
            }, "search")
            on_delta(result["text"])
            return result
        client = self.codex_client if source == "codex" else self.chat_client
        fallback_source = "chat" if source in ("tool", "search") else source
        return normalize_response(
            client.ask_stream(prompt, context, on_delta),
            "search" if network_result else fallback_source,
        )
