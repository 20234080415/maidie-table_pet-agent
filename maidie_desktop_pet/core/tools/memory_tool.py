"""将持久化 Memory 的读取能力接入 Tool 管线。

Memory 存储实现位于项目根级 ``memory`` 包；本适配器只把查询和限制参数转交给注入的
Memory 服务，并将结果统一为 ``ToolResult``，供 Executor/Synthesizer 使用。
"""

from __future__ import annotations

from typing import Any

from core.tools.base import Tool, ToolResult


class MemoryTool(Tool):
    """只读查询长期 Memory 的 Tool 适配器。

    实例由依赖注入获得 Memory 服务并随 Registry 常驻，不拥有数据库生命周期；
    查询失败由结构化错误承载，避免持久化层异常中断 Agent 循环。
    """
    name = "memory"

    def __init__(self, memory: Any) -> None:
        self.memory = memory

    def match(self, query: str) -> bool:
        return False  # Memory is selected by Planner, never by free-form matching.

    def run(self, query: str, *, kind: str = "long_term", limit: int = 20) -> ToolResult:
        data = (self.memory.get_recent()[-limit:] if kind == "recent"
                else self.memory.load_memories(limit))
        return {"type": self.name, "raw": {"kind": kind, "items": data}, "source": "local"}
