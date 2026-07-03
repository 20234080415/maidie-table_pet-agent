from __future__ import annotations

from threading import Event, Lock
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import QObject, pyqtSignal


class ConfirmationBroker(QObject):
    """Bridges worker-thread system actions to a main-thread PyQt confirmation."""

    requested = pyqtSignal(object)

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        super().__init__()
        self.timeout_seconds = timeout_seconds
        self._pending: dict[str, tuple[Event, list[bool]]] = {}
        self._lock = Lock()

    def request(self, action: str, params: dict[str, Any]) -> bool:
        request_id, event, answer = uuid4().hex, Event(), [False]
        with self._lock:
            self._pending[request_id] = (event, answer)
        self.requested.emit({"id": request_id, "action": action, "params": params})
        event.wait(self.timeout_seconds)
        with self._lock:
            self._pending.pop(request_id, None)
        return answer[0]

    def resolve(self, request_id: str, approved: bool) -> None:
        with self._lock:
            pending = self._pending.get(request_id)
        if pending:
            pending[1][0] = bool(approved)
            pending[0].set()
