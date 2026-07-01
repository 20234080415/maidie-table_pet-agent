from __future__ import annotations

from typing import Any

import requests


class NetworkClient:
    """Small requests wrapper that never lets transport errors escape."""

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = max(1, int(timeout))

    def post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> tuple[Any | None, str]:
        try:
            response = requests.post(
                url, json=payload, headers=headers or {}, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json(), ""
        except requests.Timeout:
            return None, "联网查询超时了，请稍后再试。"
        except requests.RequestException as exc:
            return None, f"联网请求失败：{exc}"
        except (ValueError, TypeError) as exc:
            return None, f"搜索服务返回了无效数据：{exc}"
        except Exception as exc:
            return None, f"联网请求发生未知错误：{exc}"
