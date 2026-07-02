class VisionError(Exception):
    """Base exception for the opt-in vision pipeline."""


class VisionConfigError(VisionError):
    """Vision provider configuration is missing or invalid."""


class VisionCaptureError(VisionError):
    """A screenshot could not be captured."""


class VisionAPIError(VisionError):
    """The remote vision service could not be called."""


class VisionParseError(VisionError):
    """The vision response was not valid structured data."""
