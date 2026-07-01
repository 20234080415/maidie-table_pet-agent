from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


ToolResult = dict[str, Any]


class Tool(ABC):
    """A deterministic capability that never invokes a language model."""

    name: str

    @abstractmethod
    def match(self, query: str) -> bool:
        """Return whether this tool handles the query."""
        raise NotImplementedError

    @abstractmethod
    def run(self, query: str) -> ToolResult:
        """Return structured data (type, raw, source), never user-facing text."""
        raise NotImplementedError
