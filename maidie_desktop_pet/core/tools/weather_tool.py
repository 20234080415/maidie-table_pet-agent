"""从 Open-Meteo 获取并短期缓存结构化天气事实。

WeatherTool 负责地点解析、HTTP 错误边界和 TTL cache；它不生成穿衣或出行建议，
复杂判断留给 Synthesizer/LLM 基于事实完成。
"""

from __future__ import annotations

import re
from time import monotonic
from typing import Any

import requests

from core.tools.base import Tool, ToolResult
from core.performance import mark


class WeatherTool(Tool):
    """按城市和日期查询天气，并在实例内维护短期缓存。

    实例随 ToolRegistry 常驻，缓存以地点和日期为 key；注入 clock/http_get 可在测试中
    覆盖 TTL、超时和异常路径而无需真实网络。
    """
    name = "weather"
    URL = "https://api.open-meteo.com/v1/forecast"
    PATTERN = re.compile(r"天气|气温|温度|下雨|weather|temperature", re.I)
    WEATHER_CODES = {0: "sunny", 1: "mainly_sunny", 2: "partly_cloudy", 3: "cloudy",
                     45: "fog", 48: "rime_fog", 51: "light_drizzle", 53: "drizzle",
                     55: "heavy_drizzle", 61: "light_rain", 63: "rain", 65: "heavy_rain",
                     71: "light_snow", 73: "snow", 75: "heavy_snow", 80: "rain_showers",
                     81: "rain_showers", 82: "heavy_showers", 95: "thunderstorm"}
    LOCATIONS = {"长沙": (28.2282, 112.9388), "深圳": (22.5431, 114.0579)}

    def __init__(self, city: str = "长沙", latitude: float = 28.2282, longitude: float = 112.9388,
                 cache_ttl_seconds: float = 600.0, clock: Any = monotonic,
                 http_get: Any | None = None) -> None:
        self.city, self.latitude, self.longitude = city, latitude, longitude
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._clock, self._http_get = clock, http_get or requests.get
        self._cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}

    def match(self, query: str) -> bool:
        return bool(self.PATTERN.search(query.strip()))

    def run(self, query: str) -> ToolResult:
        """解析地点与日期，返回天气事实或结构化网络错误。"""
        target = "tomorrow" if "明天" in query or "tomorrow" in query.lower() else "today"
        city, latitude, longitude = self._location(query)
        key = (city, target)
        now = self._clock()
        cached = self._cache.get(key)
        if cached and now - cached[0] < self.cache_ttl_seconds:
            age = round(now - cached[0], 3)
            mark(weather_cache_hit=True)
            return {"type": "weather",
                    "raw": {**cached[1], "cache_hit": True, "cache_age_seconds": age},
                    "source": "api"}
        try:
            response = self._http_get(self.URL, params={
                "latitude": latitude, "longitude": longitude,
                "current": "temperature_2m,wind_speed_10m,weather_code",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,wind_speed_10m_max",
                "forecast_days": 2, "timezone": "auto",
            }, timeout=5)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            if target == "tomorrow":
                daily = payload.get("daily", {})
                raw = {"temperature": {"min": self._at(daily.get("temperature_2m_min"), 1),
                                       "max": self._at(daily.get("temperature_2m_max"), 1)},
                       "wind": self._at(daily.get("wind_speed_10m_max"), 1),
                       "forecast": self._code(self._at(daily.get("weather_code"), 1, -1)),
                       "date": self._at(daily.get("time"), 1, "tomorrow"), "city": city}
            else:
                current = payload.get("current", {})
                raw = {"temperature": current.get("temperature_2m"), "wind": current.get("wind_speed_10m"),
                       "forecast": self._code(current.get("weather_code", -1)),
                       "date": "today", "city": city}
            self._cache[key] = (now, dict(raw))
            return {"type": "weather", "raw": {**raw, "cache_hit": False,
                                                  "cache_age_seconds": 0.0},
                    "source": "api"}
        except requests.Timeout as exc:
            mark(weather_timeout=True)
            return {"type": "weather", "raw": {"error": str(exc) or "weather request timed out",
                                                  "error_code": "weather_timeout", "date": target,
                                                  "city": city, "cache_hit": False,
                                                  "cache_age_seconds": 0.0},
                    "source": "api"}
        except Exception as exc:
            return {"type": "weather", "raw": {"error": str(exc),
                                                  "error_code": "weather_request_failed",
                                                  "date": target, "city": city,
                                                  "cache_hit": False, "cache_age_seconds": 0.0},
                    "source": "api"}

    def _location(self, query: str) -> tuple[str, float, float]:
        for city, coordinates in self.LOCATIONS.items():
            if city in query:
                return city, coordinates[0], coordinates[1]
        return self.city, self.latitude, self.longitude

    @staticmethod
    def _at(values: Any, index: int, default: Any = None) -> Any:
        return values[index] if isinstance(values, list) and len(values) > index else default

    def _code(self, value: Any) -> str:
        try:
            return self.WEATHER_CODES.get(int(value), "unknown")
        except (TypeError, ValueError):
            return "unknown"
