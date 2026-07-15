"""把 Plan 与 Tool 事实合成为 Maidie 的最终用户输出。

Synthesizer 是 Brain 中唯一允许生成自然语言的阶段：它选择 Chat/Coding LLM、处理
本地确定性降级、应用 ``MaidieStyle``，并可发出 Session 消费的结构化输出事件。
"""

from __future__ import annotations

import re
from typing import Any, Callable

from ai.client import normalize_response
from core.brain.fast_route import is_simple_time_query, is_simple_weather_query
from core.formatters import CodingAnalysisFormatter
from core.performance import mark
from core.personality import MaidieStyle
from core.prompts.synthesizer import build_synthesizer_prompt
from core.session.output_events import OutputMode


class Synthesizer:
    """将结构化执行结果转换为用户文案的唯一生产组件。

    实例随 BrainRouter 常驻，持有 LLM client、人格样式和 Coding formatter；每次调用
    不保存会话状态，所需历史和 Memory context 均由调用方显式传入。
    """

    def __init__(self, chat_client: Any, codex_client: Any | None = None,
                 style: MaidieStyle | None = None, personality_prompt: str = "",
                 coding_formatter: CodingAnalysisFormatter | None = None) -> None:
        self.chat_client = chat_client
        self.codex_client = codex_client or chat_client
        self.style = style or MaidieStyle()
        self.personality_prompt = personality_prompt
        self.coding_formatter = coding_formatter or CodingAnalysisFormatter()

    def synthesize(self, user_input: str, source: str, plan: dict[str, Any] | None,
                   tool_data: list[dict[str, Any]], memory_context: str,
                   context: list[dict[str, Any]], on_delta: Callable[[str], None] | None = None,
                   technical: bool = False,
                   output_mode: OutputMode | None = None) -> dict[str, Any]:
        """生成包含文本、情绪、动作及可选展示元数据的最终结果。

        ``tool_data`` 是 Executor 的结构化记录；简单 Tool 事实与错误优先使用本地模板，
        以减少延迟和事实漂移。``on_delta`` 存在时发送 OutputEvent payload，而非模型原文。
        """
        client = self.codex_client if technical else self.chat_client
        prompt = self._prompt(user_input, source, plan, tool_data, memory_context)
        display: dict[str, Any] = {}
        # 可确定的澄清、失败和简单事实优先本地合成，LLM 只处理需要语言推理的结果。
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
        elif (any(item.get("tool") == "search" and not item.get("ok") for item in tool_data)
              and not any(item.get("tool") == "screen" and item.get("ok")
                          for item in tool_data)):
            mark(local_response_used=True)
            normalized = self._local_fallback(source, tool_data)
        elif self._successful_coding_result(tool_data) is not None:
            mark(local_response_used=True)
            normalized, display = self._coding_analysis_response(
                user_input, source, tool_data, context, client
            )
        elif any(item.get("tool") == "coding_agent" for item in tool_data):
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
        # 所有分支经过同一人格与字段归一化出口，保证 UI 数据契约一致。
        normalized["text"] = self.style.preserve(normalized.get("text", ""))
        result = self.style.normalize_fields(normalized, source)
        if display:
            result.update(display)
        elif self._needs_long_panel(result["text"], tool_data):
            full_text = result["text"]
            result.update({
                "display_type": self._display_type(tool_data),
                "short_text": self._short_text(full_text),
                "panel_title": self._panel_title(tool_data),
                "panel_text": full_text,
                "content": {},
                "full_text": full_text,
            })
            result["text"] = result["short_text"]
        search_metadata = self._search_metadata(tool_data)
        if search_metadata is not None:
            result["sources"], result["show_sources"] = search_metadata
        if output_mode is not None:
            result["output_mode"] = output_mode.value
        if on_delta:
            if output_mode is None:
                on_delta(result["text"])
            else:
                tool = next(
                    (str(item.get("tool") or "") for item in tool_data
                     if item.get("tool")), "",
                )
                on_delta({
                    "type": "token",
                    "mode": output_mode.value,
                    "content": result["text"],
                    "source": str(result.get("source") or source),
                    "tool": tool,
                    "phase": "streaming",
                })
        return result

    @staticmethod
    def _search_metadata(
        tool_data: list[dict[str, Any]],
    ) -> tuple[list[dict[str, str]], bool] | None:
        search = next((item for item in tool_data if item.get("tool") == "search"), None)
        if search is None:
            return None
        data = search.get("data", {})
        raw = data.get("raw", {}) if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            return [], True
        sources: list[dict[str, str]] = []
        if search.get("ok"):
            for source in raw.get("sources", []) or []:
                if not isinstance(source, dict):
                    continue
                sources.append({
                    "title": str(source.get("title") or ""),
                    "url": str(source.get("url") or ""),
                    "domain": str(source.get("domain") or ""),
                })
        return sources, bool(raw.get("show_sources", True))

    @staticmethod
    def _successful_coding_result(
        tool_data: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        item = next(
            (entry for entry in tool_data
             if entry.get("tool") == "coding_agent" and entry.get("ok")),
            None,
        )
        if not item:
            return None
        data = item.get("data", {})
        return data if isinstance(data, dict) else None

    def _coding_analysis_response(
        self, user_input: str, source: str, tool_data: list[dict[str, Any]],
        context: list[dict[str, Any]], client: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        data = self._successful_coding_result(tool_data) or {}
        raw = data.get("raw") or data
        content = self.coding_formatter.format(raw)
        panel_text = self.coding_formatter.to_plain_text(content)
        short_text = "分析已经完成，重点内容已整理到结果卡片中。"
        if self._client_ready(client):
            short_prompt = (
                self.style.prompt(self.personality_prompt)
                + "\n请根据当前人格、对话语气和上下文，用一句不超过45字的自然中文告诉用户："
                  "项目只读分析已完成，详细重点已放在结果卡片中。"
                  "不要复述分析内容，不要输出JSON或Markdown。"
                + f"\n用户请求：{user_input}"
            )
            try:
                generated = normalize_response(client.ask(short_prompt, context), source)
                candidate = str(generated.get("text") or "").strip()
                if candidate and "{" not in candidate and len(candidate) <= 80:
                    short_text = candidate
            except Exception:
                pass
        return (
            {"text": short_text, "emotion": "thinking", "action": "talk",
             "state": "talking", "source": source},
            {"display_type": "coding_analysis", "short_text": short_text,
             "panel_title": "项目分析结果", "content": content,
             "panel_text": panel_text, "full_text": panel_text},
        )

    @staticmethod
    def _needs_long_panel(text: str, tool_data: list[dict[str, Any]]) -> bool:
        value = str(text or "")
        list_lines = sum(
            1 for line in value.splitlines()
            if re.match(r"\s*(?:[-*•]|\d+[.)、])\s*", line)
        )
        explicit_tool = any(
            item.get("tool") in {"search", "coding_agent"} and item.get("ok")
            for item in tool_data
        )
        return len(value) > 160 or list_lines >= 2 or explicit_tool

    @staticmethod
    def _short_text(text: str) -> str:
        value = str(text or "").strip()
        first = re.split(r"(?<=[。！？!?])", value, maxsplit=1)[0].strip()
        if not first:
            first = value
        return first if len(first) <= 90 else first[:87].rstrip() + "…"

    @staticmethod
    def _display_type(tool_data: list[dict[str, Any]]) -> str:
        tools = {str(item.get("tool", "")) for item in tool_data if item.get("ok")}
        if "search" in tools:
            return "search_result"
        if tools:
            return "tool_result"
        return "long_response"

    @staticmethod
    def _panel_title(tool_data: list[dict[str, Any]]) -> str:
        tools = {str(item.get("tool", "")) for item in tool_data if item.get("ok")}
        return "搜索结果" if "search" in tools else "详细结果"

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
            failed_coding = next((item.get("data", {}).get("raw", {}) for item in tool_data
                                  if item.get("tool") == "coding_agent"), {})
            reason = str(failed_search.get("failure_reason", ""))
            query = str(failed_search.get("query", ""))
            code = str(failed_screen.get("error_code", ""))
            detail = str(failed_screen.get("error", ""))
            coding_code = str(failed_coding.get("error_code", ""))
            if coding_code == "workspace_not_configured":
                text = "还没有配置代码工作区，请先设置 workspace.root。"
            elif coding_code == "disabled":
                text = "本地 Coding Agent 目前未启用，请先在配置中开启。"
            elif coding_code == "cli_not_found":
                text = "没有找到可用的 OpenCode/Codex，请检查是否已安装以及 command 路径。"
            elif coding_code == "timeout":
                text = "Coding Agent 超时，已终止进程树。可以缩小分析范围后再试。"
            elif coding_code == "idle_timeout":
                text = "Coding Agent 长时间没有输出，可能正在等待 OpenCode 配置。请在设置页打开 OpenCode 配置，并在可见终端中完成 /connect。"
            elif coding_code == "needs_setup":
                text = "OpenCode 还需要配置模型 provider / API Key。请在设置页打开 OpenCode 配置，并在终端中执行 /connect。"
            elif coding_code == "cancelled":
                text = "这次 Coding Agent 任务已经取消，相关进程也已清理。"
            elif failed_coding:
                text = str(failed_coding.get("error") or "本地 Coding Agent 暂时不可用。")
            elif reason == "EMPTY_QUERY":
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
                problem = raw.get("problem_context", {})
                problem = problem if isinstance(problem, dict) else {}
                error = str(problem.get("error_message") or "").strip()
                question = str(problem.get("question_text") or "").strip()
                visible = str(problem.get("visible_text") or "").strip()
                screen_text = str(raw.get("screen_text") or raw.get("screenshot_summary")
                                  or visible).strip()
                if error:
                    text = (f"我在屏幕上识别到：{error}。搜索补充资料暂时不可用；"
                            "可以先检查报错对应的代码位置、输入值和依赖版本。")
                elif question:
                    text = f"我识别到的题目是：{question}。目前只能依据屏幕内容继续分析。"
                else:
                    text = (screen_text if screen_text else
                            f"当前外部窗口是 {raw.get('window') or raw.get('app', '未知窗口')}，"
                            f"场景为 {raw.get('context', 'unknown')}。")
            elif kind == "search":
                text = str(raw.get("summary") or raw.get("error") or "暂时没查到可靠资料。")
            elif kind == "coding_agent":
                summary = str(raw.get("summary") or "只读分析已完成。").strip()
                findings = raw.get("findings") if isinstance(raw.get("findings"), list) else []
                changes = (raw.get("suggested_changes")
                           if isinstance(raw.get("suggested_changes"), list) else [])
                tests = (raw.get("tests_suggested")
                         if isinstance(raw.get("tests_suggested"), list) else [])
                parts = [summary]
                if findings:
                    parts.append("主要发现：\n- " + "\n- ".join(map(str, findings[:3])))
                if changes:
                    parts.append("优先建议：\n- " + "\n- ".join(map(str, changes[:2])))
                if tests:
                    parts.append("验证建议：" + str(tests[0]))
                text = "\n".join(parts)
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
