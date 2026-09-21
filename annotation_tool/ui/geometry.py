# annotation_tool/ui/geometry.py
"""Pure coordinate-mapping helpers between scene coords and image pixels."""
from __future__ import annotations


def scene_to_image(sx: float, sy: float, scale: float, offset) -> tuple[int, int]:
    ox, oy = offset
    return (int((sx - ox) / scale), int((sy - oy) / scale))


def image_to_scene(ix: int, iy: int, scale: float, offset) -> tuple[float, float]:
    ox, oy = offset
    return (ix * scale + ox, iy * scale + oy)


def clamp_point(x: int, y: int, w: int, h: int) -> tuple[int, int]:
    return (max(0, min(x, w - 1)), max(0, min(y, h - 1)))
