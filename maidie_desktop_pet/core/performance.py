"""收集一次 Brain 请求各阶段的轻量性能标记。

Session 在请求开始/结束时建立和提交 Trace，Router、Executor 与 Tool 只追加字段；
使用 ``contextvars`` 让后台任务互不污染，且无活动 Trace 时调用保持无副作用。
"""

from __future__ import annotations

import json
import threading
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from time import monotonic
from typing import Any


@dataclass
class PerformanceTrace:
    """一次请求的阶段耗时与诊断字段容器。"""
    request_id: str
    user_text_length: int
    executor_queue_delay_ms: float = 0.0
    route_source: str = "unknown"
    route_intent: str = "unknown"
    route_duration_ms: float = 0.0
    plan_duration_ms: float = 0.0
    tool_duration_ms: float = 0.0
    tool_name: str = ""
    synthesize_duration_ms: float = 0.0
    total_response_duration_ms: float = 0.0
    weather_cache_hit: bool = False
    weather_timeout: bool = False
    local_response_used: bool = False
    memory_extraction_skipped: bool = False
    thread_name: str = ""


_current: ContextVar[PerformanceTrace | None] = ContextVar("maidie_performance", default=None)


def begin(request_id: str, text: str, submitted_at: float) -> PerformanceTrace:
    """为当前执行上下文创建 Trace，并记录 Executor 排队延迟。"""
    trace = PerformanceTrace(
        request_id=request_id,
        user_text_length=len(text),
        executor_queue_delay_ms=round((monotonic() - submitted_at) * 1000, 3),
        thread_name=threading.current_thread().name,
    )
    _current.set(trace)
    return trace


def mark(**values: Any) -> None:
    """向当前 Trace 合并已声明指标；无活动 Trace 时安全忽略。"""
    trace = _current.get()
    if trace is None:
        return
    for key, value in values.items():
        if hasattr(trace, key):
            setattr(trace, key, value)


def finish(logger: Any, started_at: float) -> None:
    """补全总耗时、写入日志并释放当前上下文的 Trace。"""
    trace = _current.get()
    if trace is None:
        return
    trace.total_response_duration_ms = round((monotonic() - started_at) * 1000, 3)
    try:
        logger.debug("performance %s", json.dumps(asdict(trace), ensure_ascii=False))
    except Exception:
        pass
    finally:
        _current.set(None)
