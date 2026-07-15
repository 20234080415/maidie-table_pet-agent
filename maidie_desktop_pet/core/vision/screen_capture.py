"""实现 Windows 多屏环境下的显式截图范围裁剪。

``VisionService`` 按 Router 已确定的 scope 调用本模块；ScreenCapture 排除 Maidie 自身
活动窗口、校验全局坐标并把底层异常统一为 ``VisionCaptureError``，不保存图像到磁盘。
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from typing import Callable

from PIL import Image, ImageGrab

from core.vision.errors import VisionCaptureError


class ScreenCapture:
    """按全屏、外部活动窗口、鼠标附近或框选矩形捕获内存图像。

    实例无历史截图状态，可随 VisionService 常驻；注入 grabber/坐标 provider 便于测试
    多屏与边界场景，而不依赖真实桌面。
    """
    def __init__(self, grabber: Callable[..., Image.Image] | None = None,
                 cursor_provider: Callable[[], tuple[int, int]] | None = None,
                 bounds_provider: Callable[[], tuple[int, int, int, int]] | None = None,
                 active_window_bounds_provider: Callable[[], tuple[int, int, int, int]] | None = None,
                 self_pid: int | None = None) -> None:
        self._grabber = grabber or ImageGrab.grab
        self._cursor_provider = cursor_provider or self._cursor_position
        self._bounds_provider = bounds_provider or self._virtual_screen_bounds
        self._self_pid = os.getpid() if self_pid is None else self_pid
        self._active_window_bounds_provider = (
            active_window_bounds_provider or self._external_active_window_bounds
        )

    def capture_fullscreen(self) -> Image.Image:
        try:
            image = self._grabber(all_screens=True)
            if not isinstance(image, Image.Image):
                raise TypeError("capture returned no image")
            return image
        except Exception as exc:
            raise VisionCaptureError("无法获取全屏截图") from exc

    def capture_active_window(self) -> Image.Image:
        """捕获最近的可见外部窗口，并明确排除 Maidie 自身进程。"""
        try:
            bbox = self._active_window_bounds_provider()
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                raise RuntimeError("foreground window has invalid bounds")
            image = self._grabber(bbox=bbox, all_screens=True)
            if not isinstance(image, Image.Image):
                raise TypeError("capture returned no image")
            return image
        except VisionCaptureError:
            raise
        except Exception as exc:
            raise VisionCaptureError(
                "没有找到可读取的外部窗口，请先切换到目标窗口"
            ) from exc

    def _external_active_window_bounds(self) -> tuple[int, int, int, int]:
        """Return the nearest visible non-Maidie window in desktop Z order."""
        if sys.platform != "win32":
            raise RuntimeError("active-window capture is only available on Windows")
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        foreground = user32.GetForegroundWindow()

        def is_external(handle: int) -> bool:
            if not handle or not user32.IsWindowVisible(handle) or user32.IsIconic(handle):
                return False
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            return pid.value != self._self_pid

        handle = foreground if is_external(foreground) else None
        if not handle:
            candidates: list[int] = []
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def visit(candidate: int, _lparam: int) -> bool:
                if is_external(candidate) and user32.GetWindowTextLengthW(candidate) > 0:
                    candidates.append(candidate)
                    return False
                return True

            callback = callback_type(visit)
            user32.EnumWindows(callback, 0)
            handle = candidates[0] if candidates else None
        if not handle:
            raise RuntimeError("no external window is available")
        rect = wintypes.RECT()
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            raise RuntimeError("external window bounds unavailable")
        return rect.left, rect.top, rect.right, rect.bottom

    def capture_cursor_region(self, width: int = 1000,
                              height: int = 800) -> Image.Image:
        """捕获以光标为中心且夹取在虚拟屏幕内的区域。"""
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
        """校验并捕获用户框选的全局坐标矩形。"""
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
