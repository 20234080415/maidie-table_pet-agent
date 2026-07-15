"""集中构造 Synthesizer 的事实到自然语言提示词。

输入由人格、用户请求、Plan、Tool 数据和 Memory context 组成；函数只序列化上下文，
LLM 选择、失败降级和输出归一化由 ``core.brain.synthesizer`` 负责。
"""

from __future__ import annotations

import json
from typing import Any


def build_synthesizer_prompt(
    personality_prompt: str,
    user_input: str,
    source: str,
    plan: dict[str, Any] | None,
    tool_data: list[dict[str, Any]],
    memory_context: str,
) -> str:
    """把结构化 Agent 上下文组装为 Synthesizer 的单次请求 prompt。"""
    facts = json.dumps(tool_data, ensure_ascii=False, default=str)
    task = (
        "你是 Maidie 的推理与回答模块。视觉模型只负责观察，最终答案由你生成。"
        "不要假装看到视觉结构化结果未提供的内容；信息不足时说明不确定并建议下一步。"
        "代码报错要解释最可能原因并给修复建议；题目先讲思路再给答案；"
        "软件界面要给出具体下一步操作。回答具体、可执行，不过度卖萌。"
        "尽量自然地依次说明：看到了什么、问题原因或当前状态、现在可以怎么做、"
        "可复制的命令或代码，以及仍未解决时下一步该让我看哪里。不要机械输出固定标题。"
        if source == "screen" else
        "只依据下方工具数据回答，不得补全或猜测事实；数据报错或不足就可爱地说暂时没查到。"
        if source != "chat" else "这是纯桌宠聊天，不得声称读取了任何设备或外部事实。"
    )
    return (
        f"{personality_prompt}\n{task}\n"
        "你是唯一输出层。隐藏所有内部步骤，只返回 JSON，字段严格为 text、emotion、action、state。"
        "emotion 仅限 idle|happy|thinking|shy；action 仅限 talk|react|think；"
        "state 仅限 talking|idle|thinking。\n"
        f"用户：{user_input}\n计划：{json.dumps(plan or {}, ensure_ascii=False)}\n"
        f"工具数据：{facts}\n记忆：{memory_context or '无'}"
    )
