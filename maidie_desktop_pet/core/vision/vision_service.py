"""编排截图、内存预处理、Qwen VL 调用和短期 Vision cache。

``ScreenTool`` 是主要调用方；Service 根据明确 scope 选择 ScreenCapture，将压缩后的
payload 交给 Client，再更新 ``VisionSession``。它不决定是否允许截图或生成最终回答。
"""

from __future__ import annotations

import logging
import os
from time import monotonic, sleep
from typing import Callable

from core.vision.image_preprocess import preprocess_for_vl
from core.vision.errors import VisionCaptureError
from core.vision.qwen_vl_client import QwenVLClient
from core.vision.screen_capture import ScreenCapture
from core.vision.vision_context import VisionContext
from core.vision.vision_session import VisionSession


class VisionService:
    """拥有 Vision 基础依赖、短 TTL cache 与短期 Session 的应用服务。

    实例随应用运行期常驻，可由设置层 ``reconfigure``；cache 只复用同 scope 的结构化
    Context，selected region 永不缓存，``clear_session`` 同时清除两层短期状态。
    """
    def __init__(self, capture: ScreenCapture | None = None,
                 client: QwenVLClient | None = None, max_width: int | None = None,
                 jpeg_quality: int | None = None, cache_ttl_seconds: float | None = None,
                 clock: Callable[[], float] = monotonic,
                 session: VisionSession | None = None,
                 cursor_delay_seconds: float = 3.0,
                 sleeper: Callable[[float], None] = sleep,
                 default_scope: str = "active_window",
                 cursor_region_width: int = 1000,
                 cursor_region_height: int = 800) -> None:
        self.capture = capture or ScreenCapture()
        self.client = client or QwenVLClient()
        self.max_width = max_width or self._env_int("VISION_MAX_WIDTH", 1280)
        self.jpeg_quality = jpeg_quality or self._env_int("VISION_JPEG_QUALITY", 85)
        self.cache_ttl_seconds = (cache_ttl_seconds if cache_ttl_seconds is not None else
                                  self._env_float("VISION_CACHE_TTL_SECONDS", 5.0))
        self._clock = clock
        self._cached_context: VisionContext | None = None
        self._cached_at = float("-inf")
        self._cached_scope = ""
        self.session = session or VisionSession(clock)
        self.cursor_delay_seconds = max(0.0, float(cursor_delay_seconds))
        self._sleeper = sleeper
        self.default_scope = default_scope
        self.cursor_region_width = cursor_region_width
        self.cursor_region_height = cursor_region_height
        self.logger = logging.getLogger(__name__)

    def reconfigure(self, settings: dict[str, object]) -> None:
        """Apply saved UI settings while keeping environment variables authoritative."""
        self.client.api_key = os.getenv("DASHSCOPE_API_KEY") or str(settings.get("api_key", ""))
        self.client.workspace_id = (os.getenv("DASHSCOPE_WORKSPACE_ID") or
                                    str(settings.get("workspace_id", "")))
        self.client.region = os.getenv("QWEN_VL_REGION") or str(
            settings.get("region", "cn-beijing")
        )
        self.client.model = os.getenv("QWEN_VL_MODEL") or str(
            settings.get("model", "qwen3-vl-flash")
        )
        self.client.base_url = self.client.build_base_url(
            self.client.workspace_id, self.client.region
        )
        self.max_width = self._setting_int(settings, "max_width", "VISION_MAX_WIDTH", 1280)
        self.jpeg_quality = self._setting_int(
            settings, "jpeg_quality", "VISION_JPEG_QUALITY", 85
        )
        self.cache_ttl_seconds = float(self._setting_int(
            settings, "cache_ttl_seconds", "VISION_CACHE_TTL_SECONDS", 5
        ))
        self.default_scope = str(settings.get("default_scope", "active_window"))
        if self.default_scope not in {"active_window", "fullscreen", "cursor_region"}:
            self.default_scope = "active_window"
        self.cursor_region_width = self._setting_int(
            settings, "cursor_region_width", "VISION_CURSOR_REGION_WIDTH", 1000
        )
        self.cursor_region_height = self._setting_int(
            settings, "cursor_region_height", "VISION_CURSOR_REGION_HEIGHT", 800
        )
        self._cached_context = None
        self._cached_at = float("-inf")

    def capture_and_analyze(self, user_question: str, scope: str = "active_window",
                            force_refresh: bool = False,
                            selected_rect: tuple[int, int, int, int] | None = None) -> VisionContext:
        """按 scope 捕获并分析一帧，返回标准化 VisionContext。

        ``force_refresh`` 绕过同 scope 的短 TTL cache；框选模式必须提供全局矩形且不缓存。
        捕获和 provider 异常保持类型上抛，由 ScreenTool 转为稳定 Tool 错误。
        """
        now = self._clock()
        cache_allowed = scope != "selected_region"
        # 只复用同一 scope 的短期结构化结果，避免跨窗口/跨区域误用旧画面。
        if (cache_allowed and not force_refresh and self._cached_context is not None and self._cached_scope == scope and
                now - self._cached_at <= self.cache_ttl_seconds):
            self.logger.debug("vision scope=%s cache_hit=true task_type=%s confidence=%.3f",
                              scope, self._cached_context.task_type,
                              self._cached_context.confidence)
            self.session.update(self._cached_context, user_question, scope=scope)
            return self._cached_context

        # scope 已由 Router/ScreenTool 明确传入；Service 不自行扩大截图范围。
        capture_started = self._clock()
        if scope == "fullscreen":
            image = self.capture.capture_fullscreen()
        elif scope == "cursor_region":
            self.logger.debug("vision scope=cursor_region cursor_delay=%.1f",
                              self.cursor_delay_seconds)
            if self.cursor_delay_seconds:
                self._sleeper(self.cursor_delay_seconds)
            image = self.capture.capture_cursor_region(
                self.cursor_region_width, self.cursor_region_height
            )
        elif scope == "selected_region":
            if selected_rect is None:
                raise VisionCaptureError("没有收到有效的框选区域")
            image = self.capture.capture_region(*selected_rect)
        else:
            image = self.capture.capture_active_window()
        capture_latency = self._clock() - capture_started
        original_size = image.size
        data_url, image_size, jpeg_size = preprocess_for_vl(
            image, self.max_width, self.jpeg_quality
        )
        qwen_started = self._clock()
        # 远程调用只接收内存中的压缩 payload，原始 Image 不落盘。
        try:
            context = self.client.analyze_image(data_url, user_question, image_size)
        except Exception:
            self.logger.debug(
                "vision scope=%s qwen_latency=%.3f qwen_failed=true",
                scope, self._clock() - qwen_started,
            )
            raise
        qwen_latency = self._clock() - qwen_started
        if cache_allowed:
            self._cached_context, self._cached_at, self._cached_scope = context, now, scope
        self.session.update(context, user_question, scope=scope)
        self.logger.debug(
            "vision scope=%s original_size=%s compressed_size=%s jpeg_bytes=%d "
            "task_type=%s confidence=%.3f cache_hit=false capture_latency=%.3f "
            "qwen_latency=%.3f selected_region_rect=%s cursor_region_size=%s",
            scope, original_size, image_size, jpeg_size, context.task_type, context.confidence,
            capture_latency, qwen_latency, selected_rect,
            ((self.cursor_region_width, self.cursor_region_height)
             if scope == "cursor_region" else None),
        )
        return context

    def clear_session(self) -> None:
        self.session.clear()
        self._cached_context = None
        self._cached_at = float("-inf")
        self._cached_scope = ""

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except ValueError:
            return default

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except ValueError:
            return default

    @staticmethod
    def _setting_int(settings: dict[str, object], key: str, env_name: str,
                     default: int) -> int:
        value = os.getenv(env_name, str(settings.get(key, default)))
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
