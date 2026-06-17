"""Deterministic per-session mask layout + display resolution.

  * where each layer's mask lives (keyed off the origin filename): Detected and
    Labeling both use ``{origin_stem}_mask.png``;
  * which layer to display: Labeling (edits) > Detected (AI final result).
"""

from __future__ import annotations

from pathlib import Path


def mask_name(origin_filename: str) -> str:
    """Mask filename for an origin image (Detected/Labeling share it)."""
    return f"{Path(origin_filename).stem}_mask.png"


def bbox_name(origin_filename: str) -> str:
    return f"{Path(origin_filename).stem}.bbox.json"


def resolve_display_mask(*, labeling_dir, detected_dir,
                         origin_filename) -> tuple[Path | None, str]:
    """Pick the mask to display for an origin image.

    Returns (path, source):
      Labeling/<name> exists  -> (path, "labeling")
      Detected/<name> exists  -> (path, "detected")
      otherwise               -> (None, "none")
    A None dir means that layer is unavailable.
    """
    name = mask_name(origin_filename)
    if labeling_dir is not None:
        lab = Path(labeling_dir) / name
        if lab.exists():
            return lab, "labeling"
    if detected_dir is not None:
        det = Path(detected_dir) / name
        if det.exists():
            return det, "detected"
    return None, "none"
