"""Import a chroma-key horizontal pose strip as a Maidie action row."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def remove_green(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    output = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    source = rgba.load()
    target = output.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, _ = source[x, y]
            dominance = green - max(red, blue)
            if green > 110 and dominance > 68:
                continue
            alpha = 255
            if green > 90 and dominance > 18:
                alpha = round(255 * (68 - dominance) / 50)
                green = min(green, max(red, blue) + 8)
            target[x, y] = (red, green, blue, max(0, min(255, alpha)))
    return output


def normalize_transparency(image: Image.Image) -> Image.Image:
    """Zero hidden RGB in fully transparent pixels to prevent scaling halos."""
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def keep_largest_component(image: Image.Image) -> Image.Image:
    """Remove detached shadows/effects while retaining the main character."""
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    pixels = alpha.load()
    visited: set[tuple[int, int]] = set()
    largest: list[tuple[int, int]] = []
    for y in range(alpha.height):
        for x in range(alpha.width):
            if (x, y) in visited or pixels[x, y] <= 12:
                continue
            stack = [(x, y)]
            visited.add((x, y))
            component: list[tuple[int, int]] = []
            while stack:
                px, py = stack.pop()
                component.append((px, py))
                for nx in range(max(0, px - 1), min(alpha.width, px + 2)):
                    for ny in range(max(0, py - 1), min(alpha.height, py + 2)):
                        if (nx, ny) not in visited and pixels[nx, ny] > 12:
                            visited.add((nx, ny))
                            stack.append((nx, ny))
            if len(component) > len(largest):
                largest = component
    keep = set(largest)
    result = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    source, target = rgba.load(), result.load()
    for x, y in keep:
        target[x, y] = source[x, y]
    return result


def import_strip(
    source: Path,
    output: Path,
    frame_count: int,
    largest_component: bool = False,
    preserve_vertical: bool = False,
) -> list[Image.Image]:
    image = remove_green(Image.open(source))
    if image.width % frame_count:
        raise ValueError("Source width must be divisible by frame count")
    slot_width = image.width // frame_count
    crops: list[Image.Image] = []
    boxes: list[tuple[int, int, int, int]] = []
    for index in range(frame_count):
        slot = image.crop((index * slot_width, 0, (index + 1) * slot_width, image.height))
        if largest_component:
            slot = keep_largest_component(slot)
        alpha = slot.getchannel("A")
        box = alpha.point(lambda value: 255 if value > 12 else 0).getbbox()
        if not box:
            raise ValueError(f"Frame {index} is empty after chroma removal")
        boxes.append(box)
        crops.append(slot.crop(box))

    max_width = max(frame.width for frame in crops)
    global_top = min(box[1] for box in boxes)
    global_bottom = max(box[3] for box in boxes)
    max_height = max(frame.height for frame in crops)
    vertical_span = global_bottom - global_top if preserve_vertical else max_height
    scale = min(180 / max_width, 198 / vertical_span)
    frames: list[Image.Image] = []
    for crop, box in zip(crops, boxes):
        size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
        resized = crop.resize(size, Image.Resampling.LANCZOS)
        frame = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
        target_y = (
            5 + round((box[1] - global_top) * scale)
            if preserve_vertical
            else 204 - resized.height
        )
        frame.alpha_composite(resized, ((192 - resized.width) // 2, target_y))
        frames.append(normalize_transparency(frame))

    output.parent.mkdir(parents=True, exist_ok=True)
    row = Image.new("RGBA", (192 * frame_count, 208), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        row.alpha_composite(frame, (index * 192, 0))
    row = normalize_transparency(row)
    row.save(output, "WEBP", lossless=True, method=6, exact=True)
    preview = output.with_suffix(".gif")
    frames[0].save(
        preview,
        save_all=True,
        append_images=frames[1:] + [frames[-2], frames[-3]],
        duration=150,
        loop=0,
        disposal=2,
    )
    return frames


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--largest-component", action="store_true")
    parser.add_argument("--preserve-vertical", action="store_true")
    args = parser.parse_args()
    frames = import_strip(
        args.source,
        args.output,
        args.frames,
        args.largest_component,
        args.preserve_vertical,
    )
    print(json.dumps({
        "ok": True,
        "output": str(args.output.resolve()),
        "frames": len(frames),
        "frame_size": [192, 208],
    }))


if __name__ == "__main__":
    main()
