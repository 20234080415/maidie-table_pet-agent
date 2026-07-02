from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Iterator
from uuid import uuid4


class ConversationMemory:
    """SQLite-backed recent chat and long-term user memory store."""

    SENSITIVE_PATTERN = re.compile(
        r"api[_ -]?key|password|passwd|密码|口令|secret|token|bearer\s+|"
        r"sk-[a-z0-9_-]+|身份证|银行卡|信用卡|cvv|私钥|private key|"
        r"手机号|电话号码|邮箱|住址|家庭地址|病历|诊断|健康隐私|"
        r"[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b1[3-9]\d{9}\b",
        re.IGNORECASE,
    )

    def __init__(self, path: Path, limit: int = 20):
        self.path = path
        self.limit = min(20, max(1, int(limit)))
        self._lock = RLock()
        self._last_search_query = ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def set_last_search_query(self, query: str) -> None:
        """Keep retry context in memory only; it is not persisted as chat."""
        self._last_search_query = str(query).strip()

    def get_last_search_query(self) -> str:
        return self._last_search_query

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL CHECK(type IN ('chat', 'fact', 'preference')),
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at DATETIME NOT NULL,
                    UNIQUE(type, key)
                )
            """)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_priority "
                "ON memories(importance DESC, created_at DESC)"
            )

    def get_recent(self) -> list[dict[str, str]]:
        try:
            with self._lock, self._connect() as connection:
                rows = connection.execute(
                    "SELECT value, created_at FROM memories WHERE type='chat' "
                    "ORDER BY id DESC LIMIT ?", (self.limit,)
                ).fetchall()
            result = []
            for row in reversed(rows):
                payload = json.loads(row["value"])
                result.append({
                    "message": str(payload.get("message", "")),
                    "response": str(payload.get("response", "")),
                    "time": str(row["created_at"]),
                })
            return result
        except (sqlite3.Error, json.JSONDecodeError, OSError, TypeError):
            return []

    def save(self, message: str, response: str) -> None:
        if self._is_sensitive(f"{message} {response}"):
            return
        payload = json.dumps(
            {"message": str(message), "response": str(response)}, ensure_ascii=False
        )
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    "INSERT INTO memories(type, key, value, importance, created_at) "
                    "VALUES('chat', ?, ?, ?, ?)",
                    (uuid4().hex, payload, 0.1, now),
                )
                connection.execute("""
                    DELETE FROM memories WHERE type='chat' AND id NOT IN (
                        SELECT id FROM memories WHERE type='chat'
                        ORDER BY id DESC LIMIT ?
                    )
                """, (self.limit,))
        except (sqlite3.Error, OSError):
            return

    def save_memory(
        self, memory_type: str, key: str, value: str, importance: float = 0.7
    ) -> bool:
        memory_type = str(memory_type).strip().lower()
        key, value = str(key).strip(), str(value).strip()
        if memory_type not in ("fact", "preference") or not key or not value:
            return False
        if self._is_sensitive(f"{key} {value}"):
            return False
        importance = max(0.0, min(1.0, float(importance)))
        try:
            with self._lock, self._connect() as connection:
                connection.execute("""
                    INSERT INTO memories(type, key, value, importance, created_at)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(type, key) DO UPDATE SET
                        value=excluded.value,
                        importance=MAX(memories.importance, excluded.importance),
                        created_at=excluded.created_at
                """, (
                    memory_type, key[:200], value[:2000], importance,
                    datetime.now().isoformat(timespec="seconds"),
                ))
            return True
        except (sqlite3.Error, OSError, TypeError, ValueError):
            return False

    def save_extracted(self, extracted: dict[str, Any]) -> None:
        if not isinstance(extracted, dict):
            return
        for plural, memory_type, default_importance in (
            ("facts", "fact", 0.7),
            ("preferences", "preference", 0.9),
        ):
            items = extracted.get(plural, [])
            if not isinstance(items, list):
                continue
            for item in items[:20]:
                if isinstance(item, dict):
                    self.save_memory(
                        memory_type,
                        str(item.get("key", "")),
                        str(item.get("value", "")),
                        float(item.get("importance", default_importance)),
                    )

    def load_memories(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            with self._lock, self._connect() as connection:
                rows = connection.execute(
                    "SELECT type, key, value, importance, created_at FROM memories "
                    "WHERE type IN ('fact', 'preference') "
                    "ORDER BY importance DESC, created_at DESC LIMIT ?",
                    (min(20, max(1, int(limit))),),
                ).fetchall()
            return [dict(row) for row in rows]
        except (sqlite3.Error, OSError, TypeError, ValueError):
            return []

    def prompt_context(self) -> str:
        memories = self.load_memories(20)
        if not memories:
            return ""
        lines = ["用户背景信息（仅用于更贴心地回答，不要声称掌握未提供的信息）："]
        for item in memories:
            label = "偏好" if item["type"] == "preference" else "事实"
            lines.append(f"- [{label}] {item['key']}：{item['value']}")
        return "\n".join(lines)

    def clear(self) -> None:
        try:
            with self._lock, self._connect() as connection:
                connection.execute("DELETE FROM memories")
        except (sqlite3.Error, OSError):
            return

    @classmethod
    def _is_sensitive(cls, text: str) -> bool:
        return bool(cls.SENSITIVE_PATTERN.search(text))

    def can_extract(self, message: str, response: str) -> bool:
        return not self._is_sensitive(f"{message} {response}")
