"""导出 Maidie 显式触发的屏幕理解管线。

BrainRouter 决定是否及以何种 scope 使用 Vision，Capture/Service/Client 完成内存处理，
VisionSession 仅保留短期结构化上下文；本包不提供后台静默监控入口。
"""

from core.vision.errors import (VisionAPIError, VisionCaptureError, VisionConfigError,
                                VisionError, VisionParseError)
from core.vision.qwen_vl_client import QwenVLClient
from core.vision.screen_capture import ScreenCapture
from core.vision.screen_reader import ScreenReader
from core.vision.vision_context import VisionContext
from core.vision.vision_service import VisionService
from core.vision.vision_session import VisionSession
from core.vision.intent_rules import VisionScope, detect_vision_scope

__all__ = ["QwenVLClient", "ScreenCapture", "ScreenReader", "VisionAPIError",
           "VisionCaptureError", "VisionConfigError", "VisionContext", "VisionError",
           "VisionParseError", "VisionScope", "VisionService", "VisionSession",
           "detect_vision_scope"]
