"""在内存中缩放并编码发送给 Vision provider 的截图。

``VisionService`` 调用本模块限制分辨率和 JPEG 大小；函数不保存文件，也不决定截图
scope，从而保持图像处理与隐私授权边界分离。
"""

from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image


def resize_image(image: Image.Image, max_width: int = 1280) -> Image.Image:
    """按最大宽度等比缩放并返回独立 Image，不修改调用方对象。"""
    if max_width <= 0:
        raise ValueError("max_width must be positive")
    if image.width <= max_width:
        return image.copy()
    height = max(1, round(image.height * max_width / image.width))
    return image.resize((max_width, height), Image.Resampling.LANCZOS)


def encode_jpeg_base64(image: Image.Image, quality: int = 85) -> str:
    """把内存图像编码为 Vision API 可接收的 JPEG data URL。"""
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=max(1, min(100, quality)), optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def preprocess_for_vl(image: Image.Image, max_width: int = 1280,
                      quality: int = 85) -> tuple[str, tuple[int, int], int]:
    """组合缩放与编码，并返回 payload、尺寸和实际字节数。"""
    resized = resize_image(image, max_width).convert("RGB")
    data_url = encode_jpeg_base64(resized, quality)
    encoded = data_url.partition(",")[2]
    return data_url, resized.size, len(base64.b64decode(encoded))
