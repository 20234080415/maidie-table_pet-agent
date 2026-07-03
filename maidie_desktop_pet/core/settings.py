from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

from core.prompts.personality import PERSONALITY_PRESETS, build_personality_prompt

NETWORK_DEFAULTS = {
    "enabled": False,
    "timeout": 10,
    "show_sources": True,
    "search_provider": "tavily",
    "search_api_key": "",
}

PROACTIVE_DEFAULTS = {
    "enabled": False,
    "tick_seconds": 45,
    "cooldown_seconds": 900,
    "idle_trigger_seconds": 300,
    "coding_trigger_seconds": 7200,
    "random_chance": 0.05,
}

VISION_DEFAULTS = {
    "enabled": False,
    "interval_seconds": 60,
    "workspace_id": "",
    "api_key": "",
    "model": "qwen3-vl-flash",
    "region": "cn-beijing",
    "max_width": 1280,
    "jpeg_quality": 85,
    "cache_ttl_seconds": 5,
    "default_scope": "active_window",
    "cursor_region_width": 1000,
    "cursor_region_height": 800,
}
FENCE_DEFAULTS = {"show_overlay": True}
WORKSPACE_DEFAULTS = {"root": ""}
CODING_AGENT_DEFAULTS = {
    "enabled": False,
    "provider": "opencode",
    "command": "opencode",
    "timeout_seconds": 120,
    "idle_timeout_seconds": 30,
    "dry_run": True,
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
            proactive = config.setdefault("proactive", {})
            for key, value in PROACTIVE_DEFAULTS.items():
                proactive.setdefault(key, value)
            vision = config.setdefault("vision", {})
            for key, value in VISION_DEFAULTS.items():
                vision.setdefault(key, value)
            fence = config.setdefault("fence", {})
            for key, value in FENCE_DEFAULTS.items():
                fence.setdefault(key, value)
            workspace = config.setdefault("workspace", {})
            for key, value in WORKSPACE_DEFAULTS.items():
                workspace.setdefault(key, value)
            coding_agent = config.setdefault("coding_agent", {})
            for key, value in CODING_AGENT_DEFAULTS.items():
                coding_agent.setdefault(key, value)
            provider = str(coding_agent.get("provider") or "opencode").strip().lower()
            coding_agent["provider"] = provider if provider in {"opencode", "codex"} else "opencode"
            coding_agent["command"] = str(
                coding_agent.get("command") or coding_agent["provider"]
            ).strip()
            try:
                timeout = int(coding_agent.get("timeout_seconds", 120))
            except (TypeError, ValueError):
                timeout = 120
            coding_agent["timeout_seconds"] = max(1, min(600, timeout))
            coding_agent["dry_run"] = True
            return config

    def public_settings(self) -> dict[str, Any]:
        config = self.load()
        ai = config.get("ai", {})
        technical = config.get("codex", {})
        personality = config.get("personality", {})
        network = config.get("network", {})
        proactive = config.get("proactive", {})
        vision = config.get("vision", {})
        workspace = config.get("workspace", {})
        coding_agent = config.get("coding_agent", {})
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
            "proactive_enabled": bool(proactive.get("enabled", False)),
            "proactive_tick_seconds": int(proactive.get("tick_seconds", 45)),
            "proactive_cooldown_seconds": int(proactive.get("cooldown_seconds", 900)),
            "screen_awareness_enabled": bool(vision.get("enabled", False)),
            "screen_awareness_interval": int(vision.get("interval_seconds", 60)),
            "vision_workspace_id": str(vision.get("workspace_id", "")),
            "has_vision_api_key": bool(vision.get("api_key", "")),
            "vision_model": str(vision.get("model", "qwen3-vl-flash")),
            "vision_region": str(vision.get("region", "cn-beijing")),
            "vision_max_width": int(vision.get("max_width", 1280)),
            "vision_jpeg_quality": int(vision.get("jpeg_quality", 85)),
            "vision_cache_ttl_seconds": int(vision.get("cache_ttl_seconds", 5)),
            "vision_default_scope": str(vision.get("default_scope", "active_window")),
            "vision_cursor_region_width": int(vision.get("cursor_region_width", 1000)),
            "vision_cursor_region_height": int(vision.get("cursor_region_height", 800)),
            "workspace_root": str(workspace.get("root", "")),
            "coding_agent_enabled": bool(coding_agent.get("enabled", False)),
            "coding_agent_provider": str(coding_agent.get("provider", "opencode")),
            "coding_agent_command": str(coding_agent.get("command", "opencode")),
            "coding_agent_timeout_seconds": int(coding_agent.get("timeout_seconds", 120)),
            "coding_agent_idle_timeout_seconds": int(coding_agent.get("idle_timeout_seconds", 30)),
            "coding_agent_dry_run": True,
        }

    def update_user_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            config = self.load()
            ai = config.setdefault("ai", {})
            technical = config.setdefault("codex", {})
            personality = config.setdefault("personality", {})
            network = config.setdefault("network", {})
            proactive = config.setdefault("proactive", {})
            vision = config.setdefault("vision", {})
            workspace = config.setdefault("workspace", {})
            coding_agent = config.setdefault("coding_agent", {})
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
            proactive["enabled"] = bool(values.get("proactive_enabled", proactive.get("enabled", False)))
            proactive["tick_seconds"] = max(30, min(60, int(values.get("proactive_tick_seconds", proactive.get("tick_seconds", 45)))))
            proactive["cooldown_seconds"] = max(30, int(values.get("proactive_cooldown_seconds", proactive.get("cooldown_seconds", 900))))
            vision["enabled"] = bool(values.get("screen_awareness_enabled", vision.get("enabled", False)))
            vision["interval_seconds"] = max(30, min(600, int(values.get("screen_awareness_interval", vision.get("interval_seconds", 60)))))
            vision["workspace_id"] = str(values.get("vision_workspace_id", vision.get("workspace_id", ""))).strip()
            new_vision_key = str(values.get("vision_api_key", "")).strip()
            if new_vision_key:
                vision["api_key"] = new_vision_key
            vision["model"] = str(values.get("vision_model", vision.get("model", "qwen3-vl-flash"))).strip()
            vision["region"] = str(values.get("vision_region", vision.get("region", "cn-beijing"))).strip()
            vision["max_width"] = max(320, min(4096, int(values.get("vision_max_width", vision.get("max_width", 1280)))))
            vision["jpeg_quality"] = max(40, min(100, int(values.get("vision_jpeg_quality", vision.get("jpeg_quality", 85)))))
            vision["cache_ttl_seconds"] = max(0, min(60, int(values.get("vision_cache_ttl_seconds", vision.get("cache_ttl_seconds", 5)))))
            default_scope = str(values.get("vision_default_scope", vision.get("default_scope", "active_window")))
            vision["default_scope"] = default_scope if default_scope in {"active_window", "fullscreen", "cursor_region"} else "active_window"
            vision["cursor_region_width"] = max(200, min(4096, int(values.get("vision_cursor_region_width", vision.get("cursor_region_width", 1000)))))
            vision["cursor_region_height"] = max(200, min(2160, int(values.get("vision_cursor_region_height", vision.get("cursor_region_height", 800)))))
            workspace["root"] = str(values.get("workspace_root", workspace.get("root", ""))).strip()
            coding_agent["enabled"] = bool(values.get(
                "coding_agent_enabled", coding_agent.get("enabled", False)
            ))
            provider = str(values.get(
                "coding_agent_provider", coding_agent.get("provider", "opencode")
            )).strip().lower()
            coding_agent["provider"] = provider if provider in {"opencode", "codex"} else "opencode"
            command = str(values.get(
                "coding_agent_command", coding_agent.get("command", "opencode")
            )).strip()
            coding_agent["command"] = command or coding_agent["provider"]
            try:
                timeout = int(values.get(
                    "coding_agent_timeout_seconds", coding_agent.get("timeout_seconds", 120)
                ))
            except (TypeError, ValueError):
                timeout = 120
            coding_agent["timeout_seconds"] = max(1, min(600, timeout))
            # Version one is read-only regardless of UI or caller input.
            coding_agent["dry_run"] = True
            self._atomic_write(config)
            return deepcopy(config)

    def personality_prompt(self, config: dict[str, Any] | None = None) -> str:
        config = config or self.load()
        settings = config.get("personality", {})
        preset = str(settings.get("preset", "gentle_tsundere"))
        custom = str(settings.get("custom_prompt", "")).strip()
        return build_personality_prompt(preset, custom)

    def _atomic_write(self, config: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
