from __future__ import annotations

import re
from typing import Any

import requests

from core.tools.base import Tool, ToolResult


class WeatherTool(Tool):
    name = "weather"
    URL = "https://api.open-meteo.com/v1/forecast"
    PATTERN = re.compile(r"天气|气温|温度|下雨|weather|temperature", re.I)
    WEATHER_CODES = {0: "sunny", 1: "mainly_sunny", 2: "partly_cloudy", 3: "cloudy",
                     45: "fog", 48: "rime_fog", 51: "light_drizzle", 53: "drizzle",
                     55: "heavy_drizzle", 61: "light_rain", 63: "rain", 65: "heavy_rain",
                     71: "light_snow", 73: "snow", 75: "heavy_snow", 80: "rain_showers",
                     81: "rain_showers", 82: "heavy_showers", 95: "thunderstorm"}

    def __init__(self, city: str = "长沙", latitude: float = 28.2282, longitude: float = 112.9388) -> None:
        self.city, self.latitude, self.longitude = city, latitude, longitude

    def match(self, query: str) -> bool:
        return bool(self.PATTERN.search(query.strip()))

    def run(self, query: str) -> ToolResult:
        target = "tomorrow" if "明天" in query or "tomorrow" in query.lower() else "today"
        try:
            response = requests.get(self.URL, params={
                "latitude": self.latitude, "longitude": self.longitude,
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
                       "date": self._at(daily.get("time"), 1, "tomorrow"), "city": self.city}
            else:
                current = payload.get("current", {})
                raw = {"temperature": current.get("temperature_2m"), "wind": current.get("wind_speed_10m"),
                       "forecast": self._code(current.get("weather_code", -1)),
                       "date": "today", "city": self.city}
            return {"type": "weather", "raw": raw, "source": "api"}
        except Exception as exc:
            return {"type": "weather", "raw": {"error": str(exc), "date": target, "city": self.city},
                    "source": "api"}

    @staticmethod
    def _at(values: Any, index: int, default: Any = None) -> Any:
        return values[index] if isinstance(values, list) and len(values) > index else default

    def _code(self, value: Any) -> str:
        try:
            return self.WEATHER_CODES.get(int(value), "unknown")
        except (TypeError, ValueError):
            return "unknown"
