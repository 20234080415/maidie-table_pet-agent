from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from typing import Any

from animation.model_manager import AnimationModel


@dataclass(frozen=True)
class Live2DCommand:
    """A queued Viewer command; does not imply browser delivery."""

    command: str
    args: tuple[Any, ...] = ()
    fallback: bool = False
    error: str = ""

    def to_dict(self, *, submitted: bool = False) -> dict[str, Any]:
        # ``delivered`` is retained for compatibility.  It only means that
        # the command sink accepted the command, not that the Viewer ran it.
        return {
            "ok": True,
            "command": self.command,
            "args": list(self.args),
            "fallback": self.fallback,
            "error": self.error,
            "queued": True,
            "delivered": submitted,
            "submitted": submitted,
            "accepted_by_sink": submitted,
        }


class Live2DBackend:
    """Pure-Python command shell for a future Live2D Viewer transport.

    This class intentionally has no QWebEngine or desktop-window dependency.
    Commands remain queued until a future transport drains and delivers them.
    """

    SUPPORTED_STATES = frozenset({
        "idle", "speaking", "thinking", "confused", "success", "error",
        "sleepy", "dragged", "headpat",
    })
    STATE_ALIASES = {
        "idle": "idle",
        "talking": "speaking", "streaming": "speaking", "speaking": "speaking",
        "thinking": "thinking", "review": "thinking",
        "headpat": "headpat",
        "drag": "dragged", "dragged": "dragged",
        "success": "success", "happy": "success", "celebrate": "success",
        "error": "error", "failed": "error",
        "confused": "confused",
        "sleep": "sleepy", "sleepy": "sleepy",
    }

    LOCAL_QUEUE_MAXLEN = 500

    def __init__(self, command_sink: Callable[[dict[str, Any]], bool] | None = None) -> None:
        self._commands: deque[Live2DCommand] = deque(maxlen=self.LOCAL_QUEUE_MAXLEN)
        self._shutdown = False
        self._command_sink = command_sink

    @property
    def pending_commands(self) -> tuple[dict[str, Any], ...]:
        return tuple(command.to_dict() for command in self._commands)

    def drain_commands(self) -> list[dict[str, Any]]:
        commands = [command.to_dict() for command in self._commands]
        self._commands.clear()
        return commands

    def _enqueue(self, command: str, *args: Any, fallback: bool = False,
                 error: str = "") -> dict[str, Any]:
        if self._shutdown:
            return {
                "ok": False, "command": command, "args": list(args),
                "fallback": False, "error": "Live2DBackend is shut down.",
                "queued": False, "delivered": False, "submitted": False,
                "accepted_by_sink": False,
            }
        payload = Live2DCommand(command, tuple(args), fallback, error)
        result = payload.to_dict(submitted=False)
        if self._command_sink is None:
            self._commands.append(payload)
        else:
            try:
                submitted = bool(self._command_sink(result))
            except Exception as exc:
                submitted = False
                result["error"] = f"command_sink 提交失败: {exc}"
            result["delivered"] = submitted
            result["submitted"] = submitted
            result["accepted_by_sink"] = submitted
            if not submitted:
                self._commands.append(payload)
        return result

    def load_model(self, model: AnimationModel | dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(model, AnimationModel):
            source = model.model3_json
        elif isinstance(model, dict):
            source = str(model.get("model3_json", ""))
        else:
            source = str(model or "")
        if not source:
            return {
                "ok": False, "command": "loadModel", "args": [],
                "fallback": False, "error": "model3_json is required.",
                "queued": False, "delivered": False, "submitted": False,
                "accepted_by_sink": False,
            }
        return self._enqueue("loadModel", source)

    def apply_state(self, state: str, intensity: float | None = None) -> dict[str, Any]:
        requested = str(state or "").strip().lower()
        normalized = self.STATE_ALIASES.get(requested, requested)
        args: tuple[Any, ...] = (normalized,)
        if intensity is not None:
            try:
                numeric_intensity = float(intensity)
            except (TypeError, ValueError):
                return {
                    "ok": False, "command": "applySemanticState",
                    "args": [normalized, intensity], "fallback": False,
                    "error": "Intensity must be a positive finite number.",
                    "queued": False, "delivered": False, "submitted": False,
                    "accepted_by_sink": False,
                }
            if not isfinite(numeric_intensity) or numeric_intensity <= 0:
                return {
                    "ok": False, "command": "applySemanticState",
                    "args": [normalized, intensity], "fallback": False,
                    "error": "Intensity must be a positive finite number.",
                    "queued": False, "delivered": False, "submitted": False,
                    "accepted_by_sink": False,
                }
            args = (normalized, numeric_intensity)
        if normalized in self.SUPPORTED_STATES:
            return self._enqueue("applySemanticState", *args)
        fallback_args: tuple[Any, ...] = ("idle",)
        if intensity is not None:
            fallback_args = ("idle", args[1])
        return self._enqueue(
            "applySemanticState", *fallback_args, fallback=True,
            error=f"Unsupported semantic state: {state!r}; falling back to idle.",
        )

    def play_motion(self, name_or_group: str) -> dict[str, Any]:
        return self._enqueue("playMotion", str(name_or_group))

    def set_expression(self, name: str) -> dict[str, Any]:
        return self._enqueue("setExpression", str(name))

    def set_parameter(self, name: str, value: float) -> dict[str, Any]:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return {
                "ok": False, "command": "setParameter", "args": [str(name), value],
                "fallback": False, "error": "Parameter value must be numeric.",
                "queued": False, "delivered": False, "submitted": False,
                "accepted_by_sink": False,
            }
        return self._enqueue("setParameter", str(name), numeric)

    def start_mouth(self) -> dict[str, Any]:
        return self._enqueue("startMouthTest")

    def stop_mouth(self) -> dict[str, Any]:
        return self._enqueue("stopMouthTest")

    def enable_mouse_follow(self, enabled: bool) -> dict[str, Any]:
        return self._enqueue("setMouseFollow", bool(enabled))

    def reset(self) -> dict[str, Any]:
        return self._enqueue("reset")

    def shutdown(self) -> dict[str, Any]:
        if self._shutdown:
            return {
                "ok": True, "command": "shutdown", "args": [],
                "fallback": False, "error": "", "queued": False,
                "delivered": False, "submitted": False,
                "accepted_by_sink": False,
            }
        payload = self._enqueue("shutdown")
        self._shutdown = True
        return payload
