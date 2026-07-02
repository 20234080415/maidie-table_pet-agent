from __future__ import annotations


class DirectionManager:
    """Stores the pet's last meaningful horizontal facing direction."""

    def __init__(self, facing_right: bool = True) -> None:
        self.facing_right = facing_right

    def update_direction(self, dx: float) -> bool:
        """Update from horizontal displacement; zero preserves the last facing."""
        if dx > 0:
            self.facing_right = True
        elif dx < 0:
            self.facing_right = False
        return self.facing_right

    def get_scale(self) -> int:
        return 1 if self.facing_right else -1
