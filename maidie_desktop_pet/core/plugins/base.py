"""定义与核心 Agent 管线解耦的事件型 Plugin 扩展点。

Plugin 接收 ``PetController`` 广播的事件，但不自动成为 Tool；需要被 Brain 调用的能力
必须显式注册到 ``ToolRegistry`` 并经过 Executor 安全边界。
"""

from abc import ABC
from typing import Any


class Plugin(ABC):
    """Base extension point for voice, music and system-monitor plugins."""

    def on_event(self, event: str, payload: Any = None) -> None:
        pass
