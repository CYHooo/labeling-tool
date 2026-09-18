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
# "images/" subdir). Masks are looked up in two places, in order:
#   1. <folder>/masks/            (current layout)
#   2. <folder>/../masks/         (legacy layout: dataset/images + dataset/masks)
# Overlays are written next to the mask dir (<mask_dir>/../verify_overlays).
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


@dataclass
class ImageItem:
    name: str            # basename without extension
    image_path: Path
    has_mask: bool
    mask_path: Path | None = None  # existing mask file, if any


def mask_filename(name: str) -> str:
    return f"{name}_mask.png"


def _image_files(dataset_dir: Path) -> list[Path]:
    return [p for p in sorted(dataset_dir.iterdir())
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS]


def mask_dir_candidates(dataset_dir: str | Path) -> list[Path]:
    """Mask directories to search, in priority order (own subdir, then legacy)."""
    dataset_dir = Path(dataset_dir)
    return [dataset_dir / MASKS_SUBDIR, dataset_dir.parent / MASKS_SUBDIR]


def find_mask(dataset_dir: str | Path, name: str) -> Path | None:
    """Return the first existing `<name>_mask.png` among the candidate dirs.

    Matching is by exact filename, so an unrelated parent `masks/` folder is
    only used when it really holds a mask for this image."""
    for d in mask_dir_candidates(dataset_dir):
        p = d / mask_filename(name)
        if p.is_file():
            return p
    return None


def resolve_mask_dir(dataset_dir: str | Path) -> Path:
    """Directory where NEW masks of this folder are saved.

    Own `masks/` subdir if it exists; otherwise the legacy parent `masks/` if it
    already holds a mask for at least one image here; otherwise own `masks/`."""
    dataset_dir = Path(dataset_dir)
    own, legacy = mask_dir_candidates(dataset_dir)
    if own.is_dir():
        return own
    if legacy.is_dir() and any((legacy / mask_filename(p.stem)).is_file()
                               for p in _image_files(dataset_dir)):
        return legacy
    return own


def list_images(dataset_dir: str | Path) -> list[ImageItem]:
    """List image files directly inside `dataset_dir` (the chosen folder itself,
    not an `images/` subdir), each with its existing mask (see `find_mask`).
    Files inside the masks/ and verify_overlays/ subfolders are never listed."""
    dataset_dir = Path(dataset_dir)
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"folder not found: {dataset_dir}")
    items = []
    for p in _image_files(dataset_dir):
        mask_path = find_mask(dataset_dir, p.stem)
        items.append(ImageItem(name=p.stem, image_path=p,
                               has_mask=mask_path is not None, mask_path=mask_path))
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


def save_overlay(path: str | Path, image_rgb: Image.Image, mask_uint8: np.ndarray,
                 colors: dict[int, tuple] | None = None) -> None:
    """Blend class colors over the image. `colors` defaults to configs.CLASS_COLORS."""
    colors = CLASS_COLORS if colors is None else colors
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    base = np.array(image_rgb.convert("RGB")).astype(np.float32)
    if mask_uint8.shape[:2] != (image_rgb.height, image_rgb.width):
        raise ValueError(f"mask shape {mask_uint8.shape[:2]} != image (H,W) "
                         f"{(image_rgb.height, image_rgb.width)}")
    for c, color in colors.items():
        sel = mask_uint8 == c
        if sel.any():
            base[sel] = (1 - OVERLAY_ALPHA) * base[sel] + OVERLAY_ALPHA * np.array(color, np.float32)
    Image.fromarray(base.clip(0, 255).astype(np.uint8)).save(path, quality=85)


def mask_dir_of(dataset_dir: str | Path) -> Path:
    """Where masks of `dataset_dir` are saved (own or legacy masks/ dir)."""
    return resolve_mask_dir(dataset_dir)


def overlay_dir_for_mask(mask_path: str | Path) -> Path:
    """verify_overlays/ sits next to the masks/ dir the mask lives in."""
    return Path(mask_path).parent.parent / OVERLAYS_SUBDIR
