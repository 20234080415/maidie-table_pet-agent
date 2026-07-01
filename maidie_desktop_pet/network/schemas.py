from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class NetworkResult:
    ok: bool = False
    type: str = "search"
    title: str = ""
    summary: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
