from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image


def resize_image(image: Image.Image, max_width: int = 1280) -> Image.Image:
    if max_width <= 0:
        raise ValueError("max_width must be positive")
    if image.width <= max_width:
        return image.copy()
    height = max(1, round(image.height * max_width / image.width))
    return image.resize((max_width, height), Image.Resampling.LANCZOS)


def encode_jpeg_base64(image: Image.Image, quality: int = 85) -> str:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=max(1, min(100, quality)), optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def preprocess_for_vl(image: Image.Image, max_width: int = 1280,
                      quality: int = 85) -> tuple[str, tuple[int, int], int]:
    resized = resize_image(image, max_width).convert("RGB")
    data_url = encode_jpeg_base64(resized, quality)
    encoded = data_url.partition(",")[2]
    return data_url, resized.size, len(base64.b64decode(encoded))
