"""提供不依赖 LLM 的本地环境 Awareness 采集组件。

各 Tracker 只维护窗口、应用、鼠标、空闲和剪贴板的最小状态；上层通过聚合快照消费，
是否把环境信息交给 Brain/Vision 仍由明确的隐私与意图边界决定。
"""

from core.awareness.idle_detector import IdleDetector
from core.awareness.mouse_tracker import MouseTracker
from core.awareness.window_tracker import WindowTracker
from core.awareness.app_tracker import AppTracker
from core.awareness.clipboard_tracker import ClipboardTracker

__all__ = ["AppTracker", "ClipboardTracker", "IdleDetector", "MouseTracker", "WindowTracker"]
