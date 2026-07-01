"""Pair image files with same-stem mask files across two folders (offline
folder-based labeling). Mask is any image file sharing the stem, .png preferred."""

from __future__ import annotations

from pathlib import Path

from labeling_tool.core.constants import IMAGE_EXTENSIONS


def mask_for_stem(mask_dir, stem: str) -> Path | None:
    """The mask in mask_dir matching `stem` (.png preferred, else any image ext)."""
    mask_dir = Path(mask_dir)
    png = mask_dir / f"{stem}.png"
    if png.exists():
        return png
    for ext in sorted(IMAGE_EXTENSIONS):
        p = mask_dir / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def pair_by_stem(image_dir, mask_dir) -> list[tuple[str, Path | None]]:
    """(image_filename, mask_path|None) for each image in image_dir, sorted by name."""
    image_dir = Path(image_dir)
    out: list[tuple[str, Path | None]] = []
    for f in sorted(image_dir.iterdir(), key=lambda p: p.name):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
            out.append((f.name, mask_for_stem(mask_dir, f.stem)))
    return out
