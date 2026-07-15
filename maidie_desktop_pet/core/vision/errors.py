"""定义 Vision 管线各边界可稳定识别的异常类型。

Capture、配置、远程 API 与解析失败分开分类，使 ScreenTool 能映射为稳定错误码，
同时避免把 provider 细节直接泄漏到 UI。
"""

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
