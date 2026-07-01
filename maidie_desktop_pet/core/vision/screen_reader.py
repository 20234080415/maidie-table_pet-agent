from __future__ import annotations

import re
from hashlib import sha256
from time import monotonic
from typing import Any, Callable


class ScreenReader:
    """Opt-in screenshot/OCR reader. Images are processed in memory by default."""

    APP_RULES = {
        "vscode": r"visual studio code|vscode|\.py\b|\.js\b|\.ts\b",
        "chrome": r"google chrome|chrome",
        "edge": r"microsoft edge|edge",
        "wechat": r"wechat|微信",
    }
    CONTEXT_RULES = (
        ("coding", r"def |class |import |function |const |visual studio code|traceback"),
        ("chatting", r"wechat|微信|discord|slack|telegram|发送消息"),
        ("video", r"youtube|bilibili|哔哩哔哩|播放|暂停"),
        ("browsing", r"http|搜索|google|bing|chrome|edge|firefox"),
    )

    def __init__(self, enabled: bool = False, interval_seconds: float = 60.0,
                 screenshot_provider: Callable[[], Any] | None = None,
                 ocr_provider: Callable[[Any], str] | None = None,
                 clock: Callable[[], float] = monotonic) -> None:
        self.enabled = enabled
        self.interval_seconds = max(10.0, float(interval_seconds))
        self._screenshot_provider = screenshot_provider or self._grab_screen
        self._ocr_provider = ocr_provider or self._ocr
        self._clock = clock
        self._last_read = float("-inf")
        self._last_hash = ""
        self._last_result = self._empty("not_read")

    def read(self, force: bool = False) -> dict[str, Any]:
        now = self._clock()
        if not self.enabled:
            return self._empty("disabled")
        if not force and now - self._last_read < self.interval_seconds:
            return {**self._last_result, "status": "cached"}
        self._last_read = now
        try:
            image = self._screenshot_provider()
            text = str(self._ocr_provider(image) or "").strip()[:12000]
            lowered = text.lower()
            apps = [name for name, pattern in self.APP_RULES.items() if re.search(pattern, lowered, re.I)]
            context = next((name for name, pattern in self.CONTEXT_RULES if re.search(pattern, lowered, re.I)), "unknown")
            confidence = min(1.0, 0.25 + len(text) / 800) if text else 0.0
            digest = sha256(text.encode("utf-8", errors="ignore")).hexdigest() if text else ""
            changed = bool(digest and self._last_hash and digest != self._last_hash)
            self._last_hash = digest or self._last_hash
            self._last_result = {"screen_text": text, "apps_detected": apps, "context": context,
                                 "confidence": round(confidence, 3), "changed": changed}
            return dict(self._last_result)
        except Exception as exc:
            result = self._empty("error")
            result["error"] = str(exc)
            return result

    @staticmethod
    def _empty(reason: str) -> dict[str, Any]:
        return {"screen_text": "", "apps_detected": [], "context": "unknown",
                "confidence": 0.0, "changed": False, "status": reason}

    @staticmethod
    def _grab_screen() -> Any:
        from PIL import ImageGrab
        return ImageGrab.grab(all_screens=True)

    @staticmethod
    def _ocr(image: Any) -> str:
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("pytesseract is not installed") from exc
        return pytesseract.image_to_string(image, lang="chi_sim+eng")
