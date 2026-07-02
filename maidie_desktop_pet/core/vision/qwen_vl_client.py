from __future__ import annotations

import json
import os
from typing import Any, Callable

from core.vision.errors import VisionAPIError, VisionConfigError
from core.vision.vision_context import VisionContext


SYSTEM_PROMPT = """你是 Maidie 的屏幕视觉理解模块。你只负责观察截图和提取结构化信息，不负责最终回答用户。
请根据截图和用户问题，输出结构化 JSON。
只输出 JSON，不要 Markdown，不要代码块，不要解释。
字段必须包括：
screen_summary: 对屏幕内容的简短总结
visible_text: 屏幕中可读到的关键文字，尽量完整
task_type: general_screen | code_error | math_problem | document | webpage | image_question | ui_operation | unknown
important_regions: 字符串数组，描述重要区域
user_intent_guess: 根据截图和用户问题推测用户想做什么
confidence: 0.0 到 1.0 的置信度
如果看不清或信息不足，也必须输出 JSON，并把 confidence 设低。"""


class QwenVLClient:
    def __init__(self, api_key: str | None = None, workspace_id: str | None = None,
                 region: str | None = None, model: str | None = None,
                 timeout: float = 30.0, client_factory: Callable[..., Any] | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("DASHSCOPE_API_KEY", "")
        self.workspace_id = (workspace_id if workspace_id is not None else
                             os.getenv("DASHSCOPE_WORKSPACE_ID", ""))
        self.region = region or os.getenv("QWEN_VL_REGION", "cn-beijing")
        self.model = model or os.getenv("QWEN_VL_MODEL", "qwen3-vl-flash")
        self.timeout = timeout
        self.base_url = self.build_base_url(self.workspace_id, self.region)
        self._client_factory = client_factory

    @staticmethod
    def build_base_url(workspace_id: str, region: str) -> str:
        clean_workspace = str(workspace_id).strip()
        clean_region = str(region).strip() or "cn-beijing"
        return f"https://{clean_workspace}.{clean_region}.maas.aliyuncs.com/compatible-mode/v1"

    def analyze_image(self, image_data_url: str, user_question: str,
                      image_size: tuple[int, int] | None = None) -> VisionContext:
        if not self.api_key or not self.workspace_id:
            raise VisionConfigError(
                "视觉能力还没有配置好，需要先设置 DASHSCOPE_API_KEY 和 DASHSCOPE_WORKSPACE_ID。"
            )
        try:
            factory = self._client_factory
            if factory is None:
                from openai import OpenAI
                factory = OpenAI
            client = factory(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": f"用户原始问题：{user_question}"},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ]},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = str(response.choices[0].message.content or "").strip()
        except VisionConfigError:
            raise
        except Exception as exc:
            raise VisionAPIError("千问视觉服务调用失败") from exc

        try:
            parsed = json.loads(self._strip_fence(raw))
            if not isinstance(parsed, dict):
                raise ValueError("response is not an object")
            return VisionContext.from_dict(parsed, raw_response=raw, image_size=image_size)
        except (TypeError, ValueError, json.JSONDecodeError):
            return VisionContext.fallback(raw_response=raw, image_size=image_size)

    @staticmethod
    def _strip_fence(text: str) -> str:
        if text.startswith("```json") and text.endswith("```"):
            return text[7:-3].strip()
        if text.startswith("```") and text.endswith("```"):
            return text[3:-3].strip()
        return text
