from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from shutil import which
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
                 tesseract_path: str | None = None,
                 clock: Callable[[], float] = monotonic) -> None:
        self.enabled = enabled
        self.interval_seconds = max(10.0, float(interval_seconds))
        self._screenshot_provider = screenshot_provider or self._grab_screen
        self._screenshot_source = "full_screen"
        self._ocr_provider = ocr_provider or self._ocr
        self._clock = clock
        self.tesseract_path = tesseract_path
        self._last_read = float("-inf")
        self._last_hash = ""
        self._last_result = self._empty("not_read")

    def read(self, force: bool = False) -> dict[str, Any]:
        now = self._clock()
        if not self.enabled:
            result = self._empty("disabled")
            result.update({"error": "OCR is disabled", "error_code": "ocr_disabled"})
            return result
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
                                 "confidence": round(confidence, 3), "changed": changed,
                                 "status": "ok", "screenshot_source": self._screenshot_source,
                                 "ocr_enabled": True, "ocr_text_length": len(text)}
            return dict(self._last_result)
        except Exception as exc:
            result = self._empty("error")
            result.update({"error": str(exc), "error_code": "screen_read_failed"})
            return result

    def _empty(self, reason: str) -> dict[str, Any]:
        return {"screen_text": "", "apps_detected": [], "context": "unknown",
                "confidence": 0.0, "changed": False, "status": reason,
                "screenshot_source": "failed", "ocr_enabled": bool(self.enabled),
                "ocr_text_length": 0}

    @staticmethod
    def _grab_screen() -> Any:
        from PIL import ImageGrab
        return ImageGrab.grab(all_screens=True)

    def _ocr(self, image: Any) -> str:
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("pytesseract is not installed") from exc
        configured = Path(self.tesseract_path) if self.tesseract_path else None
        standard = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        executable = configured if configured and configured.exists() else standard if standard.exists() else None
        if executable:
            pytesseract.pytesseract.tesseract_cmd = str(executable)
        elif not which("tesseract"):
            raise RuntimeError("Tesseract executable was not found")
        languages = set(pytesseract.get_languages(config=""))
        selected = "+".join(language for language in ("chi_sim", "eng") if language in languages)
        if not selected:
            raise RuntimeError("No compatible Tesseract language data is installed")
        return pytesseract.image_to_string(image, lang=selected)
