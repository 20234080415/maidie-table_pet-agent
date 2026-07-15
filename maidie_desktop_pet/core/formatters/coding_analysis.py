"""把 Coding Agent 原始结构化结果整理为稳定的分析面板数据。

Formatter 不调用 LLM，也不执行代码修改；Synthesizer 使用它生成短摘要、详细内容和
纯文本回退，使 UI 与具体 CLI 输出格式解耦。
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any


class CodingAnalysisFormatter:
    """Convert coding-agent facts into a neutral display structure."""

    SECTION_TITLES = {
        "project_overview": "项目概览",
        "key_findings": "优先问题",
        "priority_suggestions": "优先建议",
        "validation_suggestions": "验证建议",
        "cautions": "注意事项",
    }

    def format(self, raw: dict[str, Any] | list[Any] | str) -> dict[str, Any]:
        data = self._as_mapping(raw)
        nested = data.get("content") or data.get("analysis") or data.get("result")
        if isinstance(nested, dict):
            data = {**data, **nested}

        summary_data = self._parse_mapping(data.get("summary"))
        if summary_data:
            data = {**data, **summary_data}

        overview = self._overview(data)
        findings = self._items(data, "key_findings", "findings", "issues", "problems")
        suggestions = self._items(
            data, "priority_suggestions", "suggested_changes", "recommendations", "priority"
        )
        validation = self._items(
            data, "validation_suggestions", "tests_suggested", "tests", "validation"
        )
        cautions = self._items(data, "cautions", "warnings", "risks", "notes")
        return {
            "project_overview": overview or "已完成当前工作区的只读分析。",
            "key_findings": findings,
            "priority_suggestions": suggestions,
            "validation_suggestions": validation,
            "cautions": cautions,
        }

    def to_plain_text(self, content: dict[str, Any]) -> str:
        sections: list[str] = []
        for key, title in self.SECTION_TITLES.items():
            value = content.get(key)
            if not value:
                continue
            if isinstance(value, list):
                body = "\n".join(f"- {item}" for item in value if str(item).strip())
            else:
                body = str(value).strip()
            if body:
                sections.append(f"{title}\n{body}")
        return "\n\n".join(sections)

    def _overview(self, data: dict[str, Any]) -> str:
        explicit = data.get("project_overview")
        if explicit:
            return self._natural_text(explicit)
        facts: list[str] = []
        name = self._natural_text(data.get("project_name"))
        project_type = self._natural_text(data.get("project_type"))
        language = self._natural_text(data.get("language") or data.get("languages"))
        total_files = data.get("total_files")
        purpose = self._natural_text(data.get("purpose"))
        summary = data.get("summary")
        if name:
            facts.append(f"项目名称为{name}")
        if project_type:
            facts.append(f"项目类型为{project_type}")
        if total_files not in (None, ""):
            facts.append(f"共包含{self._natural_text(total_files)}个文件")
        if language:
            facts.append(f"主要语言为{language}")
        if purpose:
            facts.append(f"主要用途是{purpose}")
        if facts:
            overview = "，".join(facts) + "。"
        else:
            overview = self._natural_text(summary)
        structure = self._natural_text(data.get("structure"))
        if structure:
            overview += (" " if overview else "") + f"项目结构：{structure}。"
        return overview.strip()

    def _items(self, data: dict[str, Any], *keys: str) -> list[str]:
        for key in keys:
            if key not in data or data[key] in (None, "", [], {}):
                continue
            value = data[key]
            values = value if isinstance(value, (list, tuple, set)) else [value]
            items = [self._natural_text(item) for item in values]
            return [item for item in items if item]
        return []

    def _as_mapping(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return {"findings": value}
        parsed = self._parse_mapping(value)
        return parsed or {"summary": self._natural_text(value)}

    @staticmethod
    def _parse_mapping(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        fenced = re.fullmatch(r"```(?:json|python)?\s*(.*?)\s*```", text, re.I | re.S)
        if fenced:
            text = fenced.group(1).strip()
        if not (text.startswith("{") and text.endswith("}")):
            return None
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(text)
            except (ValueError, SyntaxError, json.JSONDecodeError):
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    def _natural_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, dict):
            return "；".join(
                f"{self._label(key)}：{self._natural_text(item)}"
                for key, item in value.items() if self._natural_text(item)
            )
        if isinstance(value, (list, tuple, set)):
            return "、".join(filter(None, (self._natural_text(item) for item in value)))
        return str(value).strip()

    @staticmethod
    def _label(value: Any) -> str:
        return str(value).replace("_", " ").strip()
