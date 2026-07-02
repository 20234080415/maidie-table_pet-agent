from __future__ import annotations

import random
from dataclasses import dataclass, field
from time import monotonic
from typing import Callable

from core.movement import Bounds


@dataclass
class FenceZone:
    """Widget-free rectangular movement constraint for the whole pet window."""

    enabled: bool = False
    rect: Bounds | None = None
    padding: int = 8
    last_complain_at: float = float("-inf")
    complain_cooldown_ms: int = 5000
    clock_ms: Callable[[], float] = field(
        default=lambda: monotonic() * 1000, repr=False
    )
    chooser: Callable[[tuple[str, ...]], str] = field(default=random.choice, repr=False)

    COMPLAINTS = (
        "呜……为什么把我关起来啦！",
        "小唐哥，你这是给我画地为牢嘛？",
        "我才没有想跑出去呢……哼。",
    )

    def enable(self, rect: Bounds | tuple[float, float, float, float]) -> None:
        if not isinstance(rect, Bounds):
            rect = Bounds(*rect)
        left, right = sorted((float(rect.left), float(rect.right)))
        top, bottom = sorted((float(rect.top), float(rect.bottom)))
        self.rect = Bounds(left, top, right, bottom)
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def is_enabled(self) -> bool:
        return self.enabled and self.rect is not None

    def active_bounds(self, pet_width: float, pet_height: float,
                      fallback: Bounds) -> Bounds:
        if not self.is_enabled():
            return fallback
        assert self.rect is not None
        left = self.rect.left + self.padding
        top = self.rect.top + self.padding
        right = max(self.rect.right - self.padding, left + max(0.0, pet_width))
        bottom = max(self.rect.bottom - self.padding, top + max(0.0, pet_height))
        return Bounds(left, top, right, bottom)

    def clamp_point(self, x: float, y: float, pet_width: float,
                    pet_height: float) -> tuple[float, float]:
        if not self.is_enabled():
            return float(x), float(y)
        bounds = self.active_bounds(pet_width, pet_height, self.rect)  # type: ignore[arg-type]
        max_x = max(bounds.left, bounds.right - pet_width)
        max_y = max(bounds.top, bounds.bottom - pet_height)
        return (max(bounds.left, min(max_x, float(x))),
                max(bounds.top, min(max_y, float(y))))

    def contains_pet(self, x: float, y: float, pet_width: float,
                     pet_height: float) -> bool:
        if not self.is_enabled():
            return True
        clamped = self.clamp_point(x, y, pet_width, pet_height)
        return abs(clamped[0] - x) < 0.001 and abs(clamped[1] - y) < 0.001

    def nearest_inside_position(self, x: float, y: float, pet_width: float,
                                pet_height: float) -> tuple[float, float]:
        return self.clamp_point(x, y, pet_width, pet_height)

    def hit_test_edge(self, x: float, y: float, pet_width: float,
                      pet_height: float) -> set[str]:
        if not self.is_enabled():
            return set()
        bounds = self.active_bounds(pet_width, pet_height, self.rect)  # type: ignore[arg-type]
        edges: set[str] = set()
        if x <= bounds.left:
            edges.add("left")
        if x + pet_width >= bounds.right:
            edges.add("right")
        if y <= bounds.top:
            edges.add("top")
        if y + pet_height >= bounds.bottom:
            edges.add("bottom")
        return edges

    def should_complain(self, now_ms: float | None = None) -> bool:
        now = self.clock_ms() if now_ms is None else now_ms
        if now - self.last_complain_at < self.complain_cooldown_ms:
            return False
        self.last_complain_at = now
        return True

    def complaint_text(self) -> str:
        return self.chooser(self.COMPLAINTS)

    def enable_default(self, center_x: float, center_y: float, screen: Bounds,
                       pet_width: float, pet_height: float,
                       width: float = 360, height: float = 260) -> Bounds:
        width = min(max(width, pet_width + self.padding * 2), screen.right - screen.left)
        height = min(max(height, pet_height + self.padding * 2), screen.bottom - screen.top)
        left = max(screen.left, min(screen.right - width, center_x - width / 2))
        top = max(screen.top, min(screen.bottom - height, center_y - height / 2))
        rect = Bounds(left, top, left + width, top + height)
        self.enable(rect)
        return rect


class FenceController(FenceZone):
    """Semantic controller name retained for integration sites."""

