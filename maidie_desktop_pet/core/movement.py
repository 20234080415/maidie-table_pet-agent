from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from core.state import PetState


@dataclass
class Vec2:
    x: float = 0.0
    y: float = 0.0

    def distance_to(self, other: "Vec2") -> float:
        return hypot(other.x - self.x, other.y - self.y)


@dataclass(frozen=True)
class Bounds:
    left: float
    top: float
    right: float
    bottom: float


class MovementController:
    """Target-seeking motion with acceleration, damping and edge clamping."""

    def __init__(
        self,
        walk_speed: float = 70.0,
        run_speed: float = 175.0,
        run_threshold: float = 105.0,
        walk_threshold: float = 4.0,
        acceleration: float = 360.0,
    ) -> None:
        self.position = Vec2()
        self.velocity = Vec2()
        self.target: Vec2 | None = None
        self.desired_speed = walk_speed
        self.walk_speed = walk_speed
        self.run_speed = run_speed
        self.run_threshold = run_threshold
        self.walk_threshold = walk_threshold
        self.acceleration = acceleration
        self.window_width = 320.0
        self.window_height = 380.0

    @property
    def speed(self) -> float:
        return hypot(self.velocity.x, self.velocity.y)

    def sync_geometry(self, x: float, y: float, width: float, height: float) -> None:
        self.position = Vec2(x, y)
        self.window_width = width
        self.window_height = height

    def move_to(self, target: Vec2, run: bool = False) -> None:
        self.target = target
        self.desired_speed = self.run_speed if run else self.walk_speed

    def stop(self) -> None:
        self.target = None
        self.velocity = Vec2()

    def classify_state(self) -> PetState:
        speed = self.speed
        if speed > self.run_threshold:
            return PetState.RUN
        if speed > self.walk_threshold:
            return PetState.WALK
        return PetState.IDLE

    def tick(self, dt: float, bounds: Bounds) -> Vec2:
        dt = min(max(dt, 0.0), 0.1)
        max_x = max(bounds.left, bounds.right - self.window_width)
        max_y = max(bounds.top, bounds.bottom - self.window_height)
        self.position = Vec2(
            max(bounds.left, min(max_x, self.position.x)),
            max(bounds.top, min(max_y, self.position.y)),
        )
        if self.target is None:
            self.velocity = Vec2()
            return self.position

        goal = Vec2(
            max(bounds.left, min(max_x, self.target.x)),
            max(bounds.top, min(max_y, self.target.y)),
        )
        dx = goal.x - self.position.x
        dy = goal.y - self.position.y
        distance = hypot(dx, dy)
        if distance < 3.0:
            self.position = goal
            self.stop()
            return self.position

        target_speed = min(self.desired_speed, max(18.0, distance * 2.4))
        desired_x = dx / distance * target_speed
        desired_y = dy / distance * target_speed
        max_delta = self.acceleration * dt
        self.velocity.x += max(-max_delta, min(max_delta, desired_x - self.velocity.x))
        self.velocity.y += max(-max_delta, min(max_delta, desired_y - self.velocity.y))

        next_x = self.position.x + self.velocity.x * dt
        next_y = self.position.y + self.velocity.y * dt
        clamped_x = max(bounds.left, min(max_x, next_x))
        clamped_y = max(bounds.top, min(max_y, next_y))
        if clamped_x != next_x:
            self.velocity.x = 0.0
        if clamped_y != next_y:
            self.velocity.y = 0.0
        self.position = Vec2(clamped_x, clamped_y)
        return self.position
