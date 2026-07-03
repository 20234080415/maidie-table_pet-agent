from __future__ import annotations

from collections.abc import Iterable

from core.tools.base import Tool, ToolResult


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] | None = None) -> None:
        self.tools = list(tools or [])

    def register(self, tool: Tool) -> None:
        self.tools.append(tool)

    def get(self, name: str) -> Tool | None:
        return next((tool for tool in self.tools if tool.name == name), None)

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
            if not isinstance(result, dict) or not {"type", "raw", "source"}.issubset(result):
                raise ValueError(f"{tool.name} returned an invalid data result")
            # Defense in depth: user-facing prose is forbidden in the data layer.
            result.pop("text", None)
            return result
        except Exception as exc:
            return {"type": tool.name, "raw": {"error": str(exc), "tool": tool.name}, "source": "local"}
