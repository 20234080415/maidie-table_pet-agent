from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

from PIL import Image, ImageGrab

from core.vision.errors import VisionCaptureError


class ScreenCapture:
    def __init__(self, grabber: Callable[..., Image.Image] | None = None) -> None:
        self._grabber = grabber or ImageGrab.grab

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
