from __future__ import annotations

from collections.abc import Iterable

from core.tools.base import Tool, ToolResult


class ToolRegistry:
    """Ordered tool matcher. The first matching tool wins."""

    def __init__(self, tools: Iterable[Tool] | None = None) -> None:
        self.tools: list[Tool] = list(tools or [])

    def register(self, tool: Tool) -> None:
        self.tools.append(tool)

    def match(self, query: str) -> Tool | None:
        for tool in self.tools:
            try:
                if tool.match(query):
                    return tool
            except Exception:
                continue
        return None

    def run(self, query: str) -> ToolResult | None:
        tool = self.match(query)
        if tool is None:
            return None
        try:
            result = tool.run(query)
            required = {"type", "text", "raw", "source"}
            if not isinstance(result, dict) or not required.issubset(result):
                raise ValueError(f"{tool.name} returned an invalid result")
            return result
        except Exception as exc:
            return {
                "type": tool.name,
                "text": "工具暂时不可用，正在尝试其他方式。",
                "raw": {"error": str(exc), "tool": tool.name},
                "source": "local",
            }
