from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    duration_ms: int = 1000
    cooldown_ms: int = 0
    priority: int = 80
    state: str = "reacting"
    triggers: tuple[str, ...] = ()
    interaction_region: str | None = None
    gesture: str | None = None


class ActionRegistry:
    """Data-driven action metadata and per-action cooldown tracking."""

    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self._definitions = self._load()
        self._last_triggered: dict[str, float] = {}

    def _load(self) -> dict[str, ActionDefinition]:
        values = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {
            name: ActionDefinition(
                name=name,
                duration_ms=int(item.get("duration_ms", item.get("frames", 6) * item.get("interval", 150) + 150)),
                cooldown_ms=int(item.get("cooldown_ms", 0)),
                priority=int(item.get("priority", 80)),
                state=str(item.get("state", "reacting")),
                triggers=tuple(str(trigger).lower() for trigger in item.get("triggers", [])),
                interaction_region=item.get("interaction_region"),
                gesture=item.get("gesture"),
            )
            for name, item in values.items()
        }

    def get(self, name: str) -> ActionDefinition | None:
        return self._definitions.get(name)

    def can_trigger(self, name: str) -> bool:
        definition = self.get(name)
        if not definition:
            return False
        elapsed_ms = (monotonic() - self._last_triggered.get(name, float("-inf"))) * 1000
        return elapsed_ms >= definition.cooldown_ms

    def mark_triggered(self, name: str) -> None:
        self._last_triggered[name] = monotonic()

    def match_message(self, message: str) -> str | None:
        lowered = message.lower()
        for definition in self._definitions.values():
            if definition.triggers and self.can_trigger(definition.name):
                if any(trigger in lowered for trigger in definition.triggers):
                    return definition.name
        return None

    def public_definitions(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "duration_ms": item.duration_ms,
                "cooldown_ms": item.cooldown_ms,
                "priority": item.priority,
                "state": item.state,
            }
            for name, item in self._definitions.items()
        }
