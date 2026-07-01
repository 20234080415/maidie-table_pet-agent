from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock


class ConversationMemory:
    def __init__(self, path: Path, limit: int = 10):
        self.path = path
        self.limit = limit
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def get_recent(self) -> list[dict[str, str]]:
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data[-self.limit:] if isinstance(data, list) else []
            except (json.JSONDecodeError, OSError):
                return []

    def save(self, message: str, response: str) -> None:
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = []
            data.append({"message": message, "response": response, "time": datetime.now().isoformat(timespec="seconds")})
            self.path.write_text(json.dumps(data[-self.limit:], ensure_ascii=False, indent=2), encoding="utf-8")

    def clear(self) -> None:
        with self._lock:
            self.path.write_text("[]", encoding="utf-8")
