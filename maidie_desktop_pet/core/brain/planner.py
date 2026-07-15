"""将 Router 的意图元数据转换为可审计的 Tool 执行计划。

Planner 只描述步骤、依赖和参数，不执行副作用，也不生成面向用户的回答。确定性的
Plan schema 使 ``BrainExecutor`` 能再次验证 Router/LLM 产物并实施安全边界。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.brain.fast_route import is_coding_agent_request, is_simple_time_query, is_weather_query
from core.brain.search_query import SearchQueryResolver


class BrainPlanner:
    """Builds deterministic data plans and never produces user-facing prose."""

    DECISION = re.compile(r"适不适合|是否适合|适合.*吗|要不要|该不该|是否应该|建议|推荐|should", re.I)
    TECHNICAL_LOOKUP = re.compile(
        r"查|搜索|资料|文档|官网|是什么|什么意思|有哪些|作用|怎么用|如何(?:使用|配置)|"
        r"\b(?:search|look up|docs?|documentation|what is|what does|how (?:to|do))\b",
        re.I,
    )
    CODING_AGENT_REQUEST = re.compile(
        r"分析(?:一下)?我的项目|帮我修(?:一下)?这个\s*bug|这个模块怎么重构|"
        r"帮我生成\s*patch|帮我看看测试怎么写|这个功能应该加在哪里|"
        r"\b(?:analy[sz]e (?:my |the )?project|fix (?:this )?bug|refactor (?:this )?module|"
        r"generate (?:a )?patch|test plan)\b",
        re.I,
    )

    def plan_for_intent(self, user_input: str, intent: str, memory: Any = None,
                        attention: dict[str, Any] | None = None,
                        clipboard_text: str = "") -> dict[str, Any]:
        """为兼容 intent 构建 Plan，并附加桌宠 Attention 上下文。

        新式结构化 route 由 :meth:`plan_route` 处理；返回值始终是 Executor 可遍历的
        字典，不包含最终自然语言。
        """
        if intent in {"screen", "vision"}:
            plan = self.screen_plan(user_input)
            return self._with_attention(plan, attention)
        if intent == "code_task":
            plan = self.code_plan(user_input)
            return self._with_attention(plan, attention)
        if intent == "system_task":
            plan = self.system_plan(user_input)
            return self._with_attention(plan, attention)
        return self._with_attention(self.plan(user_input, memory, clipboard_text), attention)

    def plan_route(self, user_input: str, route: dict[str, Any]) -> dict[str, Any]:
        """把标准化 route 转成确定性 Tool Plan。

        ``task_type`` 决定 Tool 与 action，``entities`` 仅提供数据参数；实际副作用仍由
        Executor/Tool 重新校验，Router 的权限字段本身不构成授权。
        """
        task_type = str(route.get("task_type") or "none")
        entities = dict(route.get("entities") or {})
        if task_type == "time_now":
            steps = [self._step("time", "now", {"action": "now"})]
        elif task_type == "time_delta":
            params = {"action": "delta_until",
                      "target_time_text": str(entities.get("target_time_text") or ""),
                      "event": str(entities.get("event") or "")}
            steps = [self._step("time", "delta_until", params)]
        elif task_type == "weather":
            steps = [self._step("weather", "weather", {"query": user_input,
                                                          "location": str(entities.get("location") or "")})]
        elif task_type == "search":
            steps = [self._step("search", "search", {"query": str(entities.get("query") or user_input),
                                                        "query_source": "router_entity"})]
        else:
            return self.plan_for_intent(user_input, str(route.get("intent") or "chat"))
        return {"goal": str(user_input).strip(), "steps": steps}

    @staticmethod
    def _with_attention(plan: dict[str, Any], attention: dict[str, Any] | None) -> dict[str, Any]:
        if attention:
            return {**plan, "attention": dict(attention)}
        return plan

    def plan(self, user_input: str, memory: Any = None,
             clipboard_text: str = "") -> dict[str, Any]:
        text = str(user_input).strip()
        steps: list[dict[str, Any]] = []
        needs_weather = (is_weather_query(text)
                         or bool(re.search(r"天气|气温|温度|下雨|跑步|出门|穿什么|出去玩|weather|temperature", text, re.I)))
        needs_time = is_simple_time_query(text)
        if needs_weather:
            steps.append(self._step("weather", "读取天气事实", {"query": text}))
        if needs_time:
            steps.append(self._step("time", "读取本地时间", {"query": text}))
        if (not needs_weather and not needs_time
                and SearchQueryResolver.SEARCH_INTENT.search(text)):
            resolved = SearchQueryResolver().resolve(text, memory, clipboard_text)
            if not resolved.query:
                logging.getLogger(__name__).info(
                    "search_debug raw_user_text=%r resolved_search_query='' "
                    "query_source=missing selected_tool=search tavily_result_count=0 "
                    "failure_reason=EMPTY_QUERY", text,
                )
                return {"goal": text, "steps": [], "missing_search_query": True,
                        "query_source": "missing"}
            steps.append(self._step("search", "读取检索资料", {
                "query": resolved.query, "query_source": resolved.source,
            }))
        if self.DECISION.search(text):
            steps.append(self._step("memory", "读取相关偏好", {"limit": 20}))
            if len(steps) < 2:
                steps.append(self._step("memory", "读取近期上下文", {"kind": "recent", "limit": 20}))
        if not steps:
            steps.append(self._step("memory", "读取任务上下文", {"limit": 20}))
        return {"goal": text, "steps": steps}

    @staticmethod
    def screen_plan(user_input: str) -> dict[str, Any]:
        text = str(user_input).strip()
        steps = [
            BrainPlanner._step("screen", "读取当前桌面事实", {"force": True}),
            BrainPlanner._step("search", "按屏幕问题检索补充事实", {
                "query_from": "problem_context", "conditional": True,
                "query_source": "screen_problem_analyzer",
            }),
        ]
        if re.search(r"结合.*(?:之前|以前|上次)|记得.*(?:之前|上次)|memory|previous", text, re.I):
            steps.append(BrainPlanner._step("memory", "读取相关历史上下文", {
                "kind": "recent", "limit": 10,
            }))
        return {"goal": text, "steps": steps}

    @staticmethod
    def code_plan(user_input: str) -> dict[str, Any]:
        text = str(user_input).strip()
        if is_coding_agent_request(text) or BrainPlanner.CODING_AGENT_REQUEST.search(text):
            operation = BrainPlanner._coding_operation(text)
            return {"goal": text, "steps": [
                BrainPlanner._step("coding_agent", "只读分析本地代码工作区", {
                    "query": text, "operation": operation,
                })
            ]}
        if BrainPlanner.TECHNICAL_LOOKUP.search(text):
            query = f"{text} official documentation"
            return {"goal": text, "steps": [
                BrainPlanner._step("search", "读取技术文档", {"query": query})
            ]}
        return {"goal": text, "steps": [
            BrainPlanner._step("codex", "分析代码任务并给出可执行修复资料", {"query": text})
        ]}

    @staticmethod
    def _coding_operation(text: str) -> str:
        if re.search(r"patch|补丁", text, re.I):
            return "propose_patch"
        if re.search(r"测试|test plan", text, re.I):
            return "test_plan"
        if re.search(r"修.*bug|fix .*bug", text, re.I):
            return "propose_fix"
        if re.search(r"模块|重构|加在哪里|module|refactor", text, re.I):
            return "explain_module"
        return "analyze_project"

    @staticmethod
    def system_plan(user_input: str) -> dict[str, Any]:
        text = str(user_input).strip()
        action = "search_files" if re.search(r"搜索文件|查找文件|find file|search files", text, re.I) else "read_file"
        return {"goal": text, "steps": [
            BrainPlanner._step("system", "读取或检索本地系统事实", {"query": text, "operation": action})
        ]}

    @staticmethod
    def _step(tool: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"tool": tool, "action": action, "params": params}
