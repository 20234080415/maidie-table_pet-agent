"""维护 Executor 可访问的 Tool 名称到实例映射。

Registry 是 Brain 与具体能力之间的依赖注入边界；它只负责注册、查找和兼容匹配，
不决定何时调用 Tool，也不绕过 ``BrainExecutor`` 的 allowlist 与参数校验。
"""

from __future__ import annotations

from collections.abc import Iterable

from core.tools.base import Tool, ToolResult


class ToolRegistry:
    """保存进程内 Tool 实例的轻量注册表。

    通常在应用启动时构造并贯穿运行期；Tool 资源生命周期仍由各实现或上层负责。
    """
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
