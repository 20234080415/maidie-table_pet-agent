from __future__ import annotations

import json
import threading
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from time import monotonic
from typing import Any


@dataclass
class PerformanceTrace:
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
    trace = PerformanceTrace(
        request_id=request_id,
        user_text_length=len(text),
        executor_queue_delay_ms=round((monotonic() - submitted_at) * 1000, 3),
        thread_name=threading.current_thread().name,
    )
    _current.set(trace)
    return trace


def mark(**values: Any) -> None:
    trace = _current.get()
    if trace is None:
        return
    for key, value in values.items():
        if hasattr(trace, key):
            setattr(trace, key, value)


def finish(logger: Any, started_at: float) -> None:
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
