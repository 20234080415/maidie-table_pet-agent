from __future__ import annotations

import re
from typing import Any

import requests

from core.tools.base import Tool, ToolResult


class WeatherTool(Tool):
    name = "weather"
    URL = "https://api.open-meteo.com/v1/forecast"
    PATTERN = re.compile(r"天气|气温|温度|weather|temperature", re.IGNORECASE)
    WEATHER_CODES = {
        0: "晴朗", 1: "大部晴朗", 2: "局部多云", 3: "阴天",
        45: "有雾", 48: "雾凇", 51: "小毛毛雨", 53: "毛毛雨",
        55: "较强毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨",
        71: "小雪", 73: "中雪", 75: "大雪", 80: "小阵雨",
        81: "阵雨", 82: "强阵雨", 95: "雷雨", 96: "雷雨伴小冰雹",
        99: "雷雨伴冰雹",
    }

    def __init__(self, city: str = "长沙", latitude: float = 28.2282, longitude: float = 112.9388) -> None:
        self.city = city
        self.latitude = latitude
        self.longitude = longitude

    def match(self, query: str) -> bool:
        return bool(self.PATTERN.search(query.strip()))

    def run(self, query: str) -> ToolResult:
        try:
            response = requests.get(
                self.URL,
                params={
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "current": "temperature_2m,wind_speed_10m,weather_code",
                    "timezone": "auto",
                },
                timeout=5,
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            current = payload.get("current", {})
            temperature = current["temperature_2m"]
            wind_speed = current["wind_speed_10m"]
            code = int(current.get("weather_code", -1))
            status = self.WEATHER_CODES.get(code, "未知天气")
            return {
                "type": "weather",
                "text": (
                    f"{self.city}当前天气：{status}，温度 {temperature}°C，"
                    f"风速 {wind_speed} km/h。"
                ),
                "raw": payload,
                "source": "api",
            }
        except requests.Timeout as exc:
            return self._failure("天气查询超时了。", exc)
        except requests.RequestException as exc:
            return self._failure("暂时无法连接天气服务。", exc)
        except (KeyError, TypeError, ValueError) as exc:
            return self._failure("天气服务返回的数据暂时无法读取。", exc)
        except Exception as exc:
            return self._failure("天气查询暂时不可用。", exc)

    @staticmethod
    def _failure(text: str, exc: Exception) -> ToolResult:
        return {
            "type": "weather",
            "text": text,
            "raw": {"error": str(exc)},
            "source": "api",
        }
