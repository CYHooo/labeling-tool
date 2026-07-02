# annotation_tool/core/dataset_io.py
"""Filesystem IO for the annotation tool: EXIF-aware image loading and
ConcJoint-compatible mask/overlay reading & writing."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from annotation_tool.configs import (
    MASKS_SUBDIR, OVERLAYS_SUBDIR,
    CLASS_COLORS, OVERLAY_ALPHA,
)

# Image files are read directly from the selected folder (not a fixed
# "images/" subdir). Masks/overlays still go to the fixed MASKS_SUBDIR /
# OVERLAYS_SUBDIR under that folder.
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


@dataclass
class ImageItem:
    name: str            # basename without extension
    image_path: Path
    has_mask: bool


def mask_filename(name: str) -> str:
    return f"{name}_mask.png"


def list_images(dataset_dir: str | Path) -> list[ImageItem]:
    """List image files directly inside `dataset_dir` (the chosen folder itself,
    not an `images/` subdir). Mask existence is checked in the fixed masks/ subdir.
    Files inside the masks/ and verify_overlays/ subfolders are never listed."""
    dataset_dir = Path(dataset_dir)
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"folder not found: {dataset_dir}")
    mask_dir = dataset_dir / MASKS_SUBDIR
    items = []
    for p in sorted(dataset_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            name = p.stem
            items.append(ImageItem(
                name=name,
                image_path=p,
                has_mask=(mask_dir / mask_filename(name)).exists(),
            ))
    return items


def load_image_rgb(path: str | Path) -> Image.Image:
    """Load image with EXIF orientation applied (aligns with stored masks)."""
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def load_mask(path: str | Path) -> np.ndarray:
    return np.array(Image.open(path).convert("L"), dtype=np.uint8)


def save_mask(path: str | Path, mask_uint8: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(mask_uint8, dtype=np.uint8), mode="L").save(path)


def save_overlay(path: str | Path, image_rgb: Image.Image, mask_uint8: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    base = np.array(image_rgb.convert("RGB")).astype(np.float32)
    if mask_uint8.shape[:2] != (image_rgb.height, image_rgb.width):
        raise ValueError(f"mask shape {mask_uint8.shape[:2]} != image (H,W) "
                         f"{(image_rgb.height, image_rgb.width)}")
    for c, color in CLASS_COLORS.items():
        sel = mask_uint8 == c
        if sel.any():
            base[sel] = (1 - OVERLAY_ALPHA) * base[sel] + OVERLAY_ALPHA * np.array(color, np.float32)
    Image.fromarray(base.clip(0, 255).astype(np.uint8)).save(path, quality=85)


def mask_dir_of(dataset_dir: str | Path) -> Path:
    return Path(dataset_dir) / MASKS_SUBDIR


def overlay_dir_of(dataset_dir: str | Path) -> Path:
    return Path(dataset_dir) / OVERLAYS_SUBDIR
