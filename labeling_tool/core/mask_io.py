"""Mask file path resolution and decoding."""

import cv2
from pathlib import Path

from labeling_tool.core.constants import IMAGE_EXTENSIONS, MASK_NAME_SUFFIXES
from labeling_tool.core.mask_codec import decode_mask


def find_mask_path(origin_filename: str, detected_dir: str) -> str | None:
    """Locate the mask file corresponding to an origin filename."""
    stem = Path(origin_filename).stem
    detected_path = Path(detected_dir)

    exact = detected_path / origin_filename
    if exact.exists():
        return str(exact)

    for suffix in MASK_NAME_SUFFIXES:
        for ext in IMAGE_EXTENSIONS:
            candidate = detected_path / f"{stem}{suffix}{ext}"
            if candidate.exists():
                return str(candidate)

    for ext in IMAGE_EXTENSIONS:
        candidate = detected_path / f"{stem}{ext}"
        if candidate.exists():
            return str(candidate)

    return None


def load_origin_and_masks(origin_path: str, mask_path: str | None):
    """
    Load the origin image and decode the detected mask into separate
    crack / spalling uint8 layers (0 or 255).

    Returns: (origin_bgr, crack_mask_or_None, spalling_mask_or_None)
    """
    origin = cv2.imread(origin_path)
    if origin is None:
        raise FileNotFoundError(f"Cannot read origin image: {origin_path}")

    crack_mask = None
    spalling_mask = None
    if mask_path is not None:
        raw = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
        if raw is not None:
            crack_mask, spalling_mask = decode_mask(raw, mask_path=mask_path)

    return origin, crack_mask, spalling_mask
