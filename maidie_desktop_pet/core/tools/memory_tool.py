from __future__ import annotations

from typing import Any

from core.tools.base import Tool, ToolResult


class MemoryTool(Tool):
    name = "memory"

    def __init__(self, memory: Any) -> None:
        self.memory = memory

    def match(self, query: str) -> bool:
        return False  # Memory is selected by Planner, never by free-form matching.

    def run(self, query: str, *, kind: str = "long_term", limit: int = 20) -> ToolResult:
        data = (self.memory.get_recent()[-limit:] if kind == "recent"
                else self.memory.load_memories(limit))
        return {"type": self.name, "raw": {"kind": kind, "items": data}, "source": "local"}
