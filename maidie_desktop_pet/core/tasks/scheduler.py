"""持久化并按应用 tick 触发本地计划任务。

``TaskScheduler`` 管理任务记录和到期判断，把触发结果交给上层处理；它不直接调用 Brain
或修改 UI，从而让 Session 决定任务如何进入用户交互流程。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


@dataclass
class ScheduledTask:
    """一个可持久化的计划任务记录及其触发状态。"""
    id: str
    type: str
    trigger: Any
    action: str
    enabled: bool = True
    last_fired: str = ""


class TaskScheduler:
    """Small persistent scheduler for once, cron-like, and contextual tasks."""

    WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
                "周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}

    def __init__(self, path: Path | None = None, now: Callable[[], datetime] = datetime.now,
                 condition_cooldown: float = 3600.0) -> None:
        self.path, self._now = path, now
        self.condition_cooldown = max(1.0, condition_cooldown)
        self.tasks: list[ScheduledTask] = []
        self._condition_fired_at: dict[str, float] = {}
        self._load()

    def add(self, task: ScheduledTask | dict[str, Any]) -> ScheduledTask:
        if isinstance(task, dict):
            values = dict(task)
            values.setdefault("id", f"task_{uuid.uuid4().hex[:8]}")
            task = ScheduledTask(**values)
        if task.type not in {"once", "cron", "condition"}:
            raise ValueError("task type must be once, cron, or condition")
        self.tasks.append(task)
        self._save()
        return task

    def remove(self, task_id: str) -> bool:
        before = len(self.tasks)
        self.tasks = [task for task in self.tasks if task.id != task_id]
        self._save()
        return len(self.tasks) != before

    def tick(self, context: dict[str, Any] | None = None, now: datetime | None = None) -> list[ScheduledTask]:
        """计算本次 tick 到期任务，并持久化触发/禁用状态。

        返回值只描述到期项，实际提醒或 Tool 调用由 ProactiveRuntime/PetController 执行；
        注入 ``now`` 使 cron、once 和条件冷却可确定测试。
        """
        current, context = now or self._now(), context or {}
        due = []
        for task in self.tasks:
            if not task.enabled or not self._is_due(task, current, context):
                continue
            due.append(task)
            task.last_fired = current.isoformat()
            if task.type == "once":
                task.enabled = False
            if task.type == "condition":
                self._condition_fired_at[task.id] = current.timestamp()
        if due:
            self._save()
        return due

    def _is_due(self, task: ScheduledTask, now: datetime, context: dict[str, Any]) -> bool:
        if task.type == "once":
            target = task.trigger if isinstance(task.trigger, datetime) else datetime.fromisoformat(str(task.trigger))
            return now >= target
        if task.type == "cron":
            day, hour, minute = self._parse_cron(task.trigger)
            if day is not None and now.weekday() != day:
                return False
            if (now.hour, now.minute) < (hour, minute):
                return False
            if task.last_fired:
                last = datetime.fromisoformat(task.last_fired)
                if last.date() == now.date() and (last.hour, last.minute) >= (hour, minute):
                    return False
            return True
        last = self._condition_fired_at.get(task.id, float("-inf"))
        return now.timestamp() - last >= self.condition_cooldown and self._condition_matches(task.trigger, context)

    def _parse_cron(self, trigger: Any) -> tuple[int | None, int, int]:
        if isinstance(trigger, dict):
            day = trigger.get("weekday")
            return (self.WEEKDAYS.get(str(day).lower()) if day is not None else None,
                    int(trigger.get("hour", 0)), int(trigger.get("minute", 0)))
        text = str(trigger).lower().replace("daily@", "").replace("weekly@", "")
        pieces = text.split()
        day = self.WEEKDAYS.get(pieces[0]) if len(pieces) > 1 else None
        clock = pieces[-1]
        hour, minute = (int(value) for value in clock.split(":", 1))
        return day, hour, minute

    @staticmethod
    def _condition_matches(trigger: Any, context: dict[str, Any]) -> bool:
        if callable(trigger):
            return bool(trigger(context))
        if not isinstance(trigger, dict):
            return False
        if "idle_seconds" in trigger and float(context.get("idle_time", 0)) < float(trigger["idle_seconds"]):
            return False
        if "window_state" in trigger and context.get("window_state") != trigger["window_state"]:
            return False
        if "weather" in trigger:
            weather = context.get("weather", {})
            if trigger["weather"] not in str(weather.get("forecast", "")):
                return False
        return bool(trigger)

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            self.tasks = [ScheduledTask(**item) for item in json.loads(self.path.read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError):
            self.tasks = []

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps([asdict(task) for task in self.tasks], ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.path)
