"""定义所有内置 Tool 共享的最小接口和结果数据契约。

``BrainExecutor`` 依赖该抽象而非具体实现；Tool 必须保持确定性边界并返回结构化数据，
最终文案统一由 Synthesizer 生成。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


ToolResult = dict[str, Any]


class Tool(ABC):
    """不调用 LLM、只返回结构化事实的确定性能力接口。"""

    name: str

    @abstractmethod
    def match(self, query: str) -> bool:
        """Return whether this tool handles the query."""
        raise NotImplementedError

    @abstractmethod
    def run(self, query: str) -> ToolResult:
        """Return structured data (type, raw, source), never user-facing text."""
        raise NotImplementedError
