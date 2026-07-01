class AnimationBackend:
    """Backend contract shared by sprite atlases and future Live2D engines."""

    def set_animation(self, name: str) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError
