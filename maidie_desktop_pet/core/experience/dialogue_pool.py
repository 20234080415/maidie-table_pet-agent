from __future__ import annotations

import random
from typing import Callable


class DialoguePool:
    """Pure-Python event dialogue selector with per-event repeat avoidance."""

    DEFAULTS = {
        "fence_enabled": (
            "呜……你给我画活动范围啦？", "好嘛好嘛，我就在这里活动。",
            "小唐哥，你这是给我画地为牢嘛？", "哼，我才不是想乱跑呢。",
            "这里就是我的活动区了吗？",
        ),
        "fence_disabled": (
            "哼，终于放我出来啦！", "自由啦！", "那我可以到处走走了吧？",
            "我就说嘛，还是外面舒服。", "好耶，我又可以巡逻啦！",
        ),
        "fence_snapback": (
            "呜……怎么又把我弹回来啦！", "就差一点点嘛……",
            "我才没有想跑出去呢……哼。", "这个边界也太认真了吧？",
            "好啦，我回来就是了。",
        ),
        "fence_edge_complain": (
            "这边不能走了吗？", "围栏在提醒我回头呢。", "哼，这里有空气墙。",
            "我知道啦，不往外走了。", "边界就在这里呀？",
        ),
    }

    def __init__(self, pools: dict[str, tuple[str, ...]] | None = None,
                 chooser: Callable[[tuple[str, ...]], str] = random.choice) -> None:
        self._pools = dict(self.DEFAULTS)
        if pools:
            self._pools.update({key: tuple(values) for key, values in pools.items()})
        self._chooser = chooser
        self._last: dict[str, str] = {}
        self.last_avoided_repeat = False

    def get(self, event: str) -> str:
        phrases = self._pools.get(event, ())
        if not phrases:
            raise KeyError(f"unknown dialogue event: {event}")
        previous = self._last.get(event)
        candidates = tuple(value for value in phrases if value != previous)
        self.last_avoided_repeat = previous is not None and len(phrases) > 1
        selected = self._chooser(candidates or phrases)
        self._last[event] = selected
        return selected

    def phrases(self, event: str) -> tuple[str, ...]:
        return self._pools.get(event, ())
