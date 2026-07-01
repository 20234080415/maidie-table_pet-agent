from abc import ABC
from typing import Any


class Plugin(ABC):
    """Base extension point for voice, music and system-monitor plugins."""

    def on_event(self, event: str, payload: Any = None) -> None:
        pass
