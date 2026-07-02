from __future__ import annotations

import logging
import os
from time import monotonic
from typing import Callable

from core.vision.image_preprocess import preprocess_for_vl
from core.vision.qwen_vl_client import QwenVLClient
from core.vision.screen_capture import ScreenCapture
from core.vision.vision_context import VisionContext


class VisionService:
    def __init__(self, capture: ScreenCapture | None = None,
                 client: QwenVLClient | None = None, max_width: int | None = None,
                 jpeg_quality: int | None = None, cache_ttl_seconds: float | None = None,
                 clock: Callable[[], float] = monotonic) -> None:
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
        self.logger = logging.getLogger(__name__)

    def capture_and_analyze(self, user_question: str,
                            scope: str = "active_window") -> VisionContext:
        now = self._clock()
        if (self._cached_context is not None and self._cached_scope == scope and
                now - self._cached_at <= self.cache_ttl_seconds):
            self.logger.debug("vision scope=%s cache_hit=true task_type=%s confidence=%.3f",
                              scope, self._cached_context.task_type,
                              self._cached_context.confidence)
            return self._cached_context

        image = (self.capture.capture_fullscreen() if scope == "fullscreen" else
                 self.capture.capture_active_window())
        original_size = image.size
        data_url, image_size, jpeg_size = preprocess_for_vl(
            image, self.max_width, self.jpeg_quality
        )
        context = self.client.analyze_image(data_url, user_question, image_size)
        self._cached_context, self._cached_at, self._cached_scope = context, now, scope
        self.logger.debug(
            "vision scope=%s original_size=%s compressed_size=%s jpeg_bytes=%d "
            "task_type=%s confidence=%.3f cache_hit=false",
            scope, original_size, image_size, jpeg_size, context.task_type, context.confidence,
        )
        return context

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
