"""Bounded observation analysis for choosing validated recovery actions."""

from __future__ import annotations

import json
from typing import Any

class ToolRecoveryAnalyzer:
    """Offer safe recovery options, then let the LLM choose only among those options."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def decide(self, user_input: str, plan: dict[str, Any],
               executions: list[dict[str, Any]], iteration: int,
               context: list[dict[str, Any]]) -> dict[str, Any]:
        options = self._options(plan, executions)
        if not options:
            return {"finished": True, "next_action": "finish"}
        latest_raw = self._raw(executions[-1]) if executions else {}
        payload = {
            "user_goal": str(user_input),
            "task_goal": str(plan.get("task_goal") or "none"),
            "iteration": int(iteration),
            "observation": {
                key: latest_raw.get(key)
                for key in ("ok", "operation", "path", "error_code", "observation",
                            "recoverable", "suggestions", "items", "result_count")
                if key in latest_raw
            },
            "options": [
                {"id": item["id"], "operation": item["operation"],
                 "description": item["description"]}
                for item in options
            ],
        }
        selected = self._select(payload, context)
        option = next((item for item in options if item["id"] == selected), options[0])
        return {
            "finished": False,
            "next_action": option["id"],
            "tool": option["tool"],
            "operation": option["operation"],
            "params": dict(option["params"]),
            "progress": option["progress"],
        }

    def _options(self, plan: dict[str, Any],
                 executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not executions:
            return []
        latest = executions[-1]
        raw = self._raw(latest)
        operation = str(raw.get("operation") or "")
        if not latest.get("ok") and raw.get("recoverable") and operation in {
                "read_file", "read_text_file"}:
            path = str(raw.get("path") or "")
            directory, pattern = self._similar_search(path)
            if directory and pattern:
                return [{
                    "id": "search_files", "tool": "system", "operation": "search_files",
                    "description": "search the same directory for the same filename stem",
                    "params": {"source": directory, "pattern": pattern, "limit": 50},
                    "progress": "没有找到目标文件，正在寻找相似文件...",
                }]
        if latest.get("ok") and operation == "search_files":
            items = raw.get("items") if isinstance(raw.get("items"), list) else []
            candidate = next((item for item in items if isinstance(item, dict)
                              and item.get("path")), None)
            original = self._original_failed_read(executions)
            if candidate is not None and original:
                return [{
                    "id": "read_file", "tool": "system", "operation": "read_file",
                    "description": "read the closest candidate after explicit user confirmation",
                    "params": {
                        "source": str(candidate.get("path") or ""),
                        "goal": str(plan.get("task_goal") or "none"),
                        "recovery_original_path": original,
                    },
                    "progress": "找到相似文件，等待确认后读取...",
                }]
        return []

    def _select(self, payload: dict[str, Any], context: list[dict[str, Any]]) -> str:
        try:
            if hasattr(self.client, "decide_recovery"):
                raw = self.client.decide_recovery(payload)
            else:
                return str(payload.get("options", [{}])[0].get("id") or "finish")
            parsed = self._parse(raw)
            return str(parsed.get("next_action") or "finish")
        except Exception:
            return ""

    @staticmethod
    def _parse(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict) and "next_action" in raw:
            return raw
        text = str(raw.get("text") if isinstance(raw, dict) else raw).strip()
        if text.startswith("```json") and text.endswith("```"):
            text = text[7:-3].strip()
        elif text.startswith("```") and text.endswith("```"):
            text = text[3:-3].strip()
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _raw(execution: dict[str, Any]) -> dict[str, Any]:
        data = execution.get("data") if isinstance(execution.get("data"), dict) else {}
        raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
        return raw

    @classmethod
    def _original_failed_read(cls, executions: list[dict[str, Any]]) -> str:
        for execution in executions:
            raw = cls._raw(execution)
            if (not execution.get("ok")
                    and raw.get("operation") in {"read_file", "read_text_file"}):
                return str(raw.get("path") or "")
        return ""

    @staticmethod
    def _similar_search(path: str) -> tuple[str, str]:
        normalized = str(path).strip().replace("\\", "/")
        if not normalized:
            return "", ""
        directory, separator, filename = normalized.rpartition("/")
        if not separator:
            directory, filename = ".", normalized
        stem = filename.rsplit(".", 1)[0].strip()
        return (directory or ".", f"{stem}.*") if stem else ("", "")
