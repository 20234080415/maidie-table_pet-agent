from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any


PERSONALITY_PRESETS = {
    "gentle_tsundere": ("温柔傲娇", "温柔体贴，带一点不坦率的小傲娇，亲近但不过分黏人。"),
    "cheerful": ("元气活泼", "开朗、有活力、喜欢鼓励主人，语气轻快俏皮。"),
    "healing": ("安静治愈", "安静、柔软、有耐心，像陪在身边的小小安心感。"),
    "elegant_maid": ("优雅女仆", "礼貌优雅、认真可靠，偶尔流露可爱的少女心。"),
    "custom": ("自定义", ""),
}

NETWORK_DEFAULTS = {
    "enabled": False,
    "timeout": 10,
    "show_sources": True,
    "search_provider": "tavily",
    "search_api_key": "",
}


class ConfigStore:
    """Thread-safe JSON settings with atomic replacement and secret-safe views."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            config = json.loads(self.path.read_text(encoding="utf-8"))
            network = config.setdefault("network", {})
            for key, value in NETWORK_DEFAULTS.items():
                network.setdefault(key, value)
            return config

    def public_settings(self) -> dict[str, Any]:
        config = self.load()
        ai = config.get("ai", {})
        technical = config.get("codex", {})
        personality = config.get("personality", {})
        network = config.get("network", {})
        key = str(ai.get("api_key", ""))
        return {
            "provider": ai.get("provider", "deepseek"),
            "base_url": ai.get("base_url", "https://api.deepseek.com"),
            "chat_model": ai.get("model", "deepseek-v4-flash"),
            "technical_model": technical.get("model", "deepseek-v4-pro"),
            "personality_preset": personality.get("preset", "gentle_tsundere"),
            "custom_personality": personality.get("custom_prompt", ""),
            "has_api_key": bool(key and key != "YOUR_API_KEY_HERE"),
            "network_enabled": bool(network.get("enabled", False)),
            "network_timeout": int(network.get("timeout", 10)),
            "network_show_sources": bool(network.get("show_sources", True)),
            "network_search_provider": str(network.get("search_provider", "tavily")),
            "has_network_api_key": bool(network.get("search_api_key", "")),
        }

    def update_user_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            config = self.load()
            ai = config.setdefault("ai", {})
            technical = config.setdefault("codex", {})
            personality = config.setdefault("personality", {})
            network = config.setdefault("network", {})
            ai["provider"] = str(values.get("provider", ai.get("provider", "deepseek")))
            ai["base_url"] = str(values.get("base_url", ai.get("base_url", ""))).rstrip("/")
            ai["model"] = str(values.get("chat_model", ai.get("model", "")))
            technical["base_url"] = ai["base_url"]
            technical["model"] = str(values.get("technical_model", technical.get("model", "")))
            personality["preset"] = str(values.get("personality_preset", "gentle_tsundere"))
            personality["custom_prompt"] = str(values.get("custom_personality", "")).strip()
            new_key = str(values.get("api_key", "")).strip()
            if new_key:
                ai["api_key"] = new_key
                technical["api_key"] = new_key
            network["enabled"] = bool(values.get("network_enabled", network.get("enabled", False)))
            network["timeout"] = max(1, int(values.get("network_timeout", network.get("timeout", 10))))
            network["show_sources"] = bool(values.get("network_show_sources", network.get("show_sources", True)))
            network["search_provider"] = str(values.get("network_search_provider", network.get("search_provider", "tavily")))
            new_search_key = str(values.get("network_search_api_key", "")).strip()
            if new_search_key:
                network["search_api_key"] = new_search_key
            self._atomic_write(config)
            return deepcopy(config)

    def personality_prompt(self, config: dict[str, Any] | None = None) -> str:
        config = config or self.load()
        settings = config.get("personality", {})
        preset = settings.get("preset", "gentle_tsundere")
        custom = str(settings.get("custom_prompt", "")).strip()
        if preset == "custom" and custom:
            return custom
        return PERSONALITY_PRESETS.get(preset, PERSONALITY_PRESETS["gentle_tsundere"])[1]

    def _atomic_write(self, config: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
