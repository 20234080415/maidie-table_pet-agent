from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

from PIL import Image, ImageGrab

from core.vision.errors import VisionCaptureError


class ScreenCapture:
    def __init__(self, grabber: Callable[..., Image.Image] | None = None,
                 cursor_provider: Callable[[], tuple[int, int]] | None = None,
                 bounds_provider: Callable[[], tuple[int, int, int, int]] | None = None) -> None:
        self._grabber = grabber or ImageGrab.grab
        self._cursor_provider = cursor_provider or self._cursor_position
        self._bounds_provider = bounds_provider or self._virtual_screen_bounds

    def capture_fullscreen(self) -> Image.Image:
        try:
            image = self._grabber(all_screens=True)
            if not isinstance(image, Image.Image):
                raise TypeError("capture returned no image")
            return image
        except Exception as exc:
            raise VisionCaptureError("无法获取全屏截图") from exc

    def capture_active_window(self) -> Image.Image:
        try:
            if sys.platform != "win32":
                raise RuntimeError("active-window capture is only available on Windows")
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            rect = wintypes.RECT()
            if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                raise RuntimeError("foreground window bounds unavailable")
            bbox = (rect.left, rect.top, rect.right, rect.bottom)
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                raise RuntimeError("foreground window has invalid bounds")
            image = self._grabber(bbox=bbox, all_screens=True)
            if not isinstance(image, Image.Image):
                raise TypeError("capture returned no image")
            return image
        except Exception:
            return self.capture_fullscreen()

    def capture_cursor_region(self, width: int = 1000,
                              height: int = 800) -> Image.Image:
        try:
            if width <= 0 or height <= 0:
                raise ValueError("cursor region dimensions must be positive")
            cursor_x, cursor_y = self._cursor_provider()
            left, top, right, bottom = self._bounds_provider()
            screen_width, screen_height = right - left, bottom - top
            crop_width, crop_height = min(width, screen_width), min(height, screen_height)
            crop_left = max(left, min(cursor_x - crop_width // 2, right - crop_width))
            crop_top = max(top, min(cursor_y - crop_height // 2, bottom - crop_height))
            bbox = (crop_left, crop_top, crop_left + crop_width, crop_top + crop_height)
            image = self._grabber(bbox=bbox, all_screens=True)
            if not isinstance(image, Image.Image):
                raise TypeError("capture returned no image")
            return image
        except Exception:
            return self.capture_active_window()

    def capture_region(self, x: int, y: int, width: int,
                       height: int) -> Image.Image:
        if width < 20 or height < 20:
            raise VisionCaptureError("框选区域太小")
        try:
            left, top, right, bottom = self._bounds_provider()
            crop_left = max(left, min(int(x), right - 1))
            crop_top = max(top, min(int(y), bottom - 1))
            crop_right = min(right, max(crop_left + 1, int(x) + int(width)))
            crop_bottom = min(bottom, max(crop_top + 1, int(y) + int(height)))
            if crop_right - crop_left < 20 or crop_bottom - crop_top < 20:
                raise VisionCaptureError("框选区域超出有效屏幕范围")
            image = self._grabber(
                bbox=(crop_left, crop_top, crop_right, crop_bottom), all_screens=True
            )
            if not isinstance(image, Image.Image):
                raise TypeError("capture returned no image")
            return image
        except VisionCaptureError:
            raise
        except Exception as exc:
            raise VisionCaptureError("无法截取框选区域") from exc

    @staticmethod
    def _cursor_position() -> tuple[int, int]:
        if sys.platform != "win32":
            raise RuntimeError("cursor capture is only available on Windows")
        point = wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            raise RuntimeError("cursor position unavailable")
        return point.x, point.y

    @staticmethod
    def _virtual_screen_bounds() -> tuple[int, int, int, int]:
        if sys.platform != "win32":
            raise RuntimeError("screen bounds are only available on Windows")
        user32 = ctypes.windll.user32
        left = user32.GetSystemMetrics(76)
        top = user32.GetSystemMetrics(77)
        width = user32.GetSystemMetrics(78)
        height = user32.GetSystemMetrics(79)
        if width <= 0 or height <= 0:
            raise RuntimeError("virtual screen bounds unavailable")
        return left, top, left + width, top + height
