"""Deterministic per-session mask layout + display resolution + rebuild output.

Single source of truth for the Viewer API tool's data loading:
  * where each layer's mask/bbox lives (keyed off the origin filename -- no fuzzy
    matching): Detected/Rebuilt/Labeling all use ``{origin_stem}_mask.png``;
  * which layer to display: Labeling > fresh Rebuilt > needs_rebuild, where
    "fresh" means the Rebuilt cache is not older than its Detected source;
  * how a Rebuilt mask is built: crack (R) intensity-refined, non-crack (G) kept.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from labeling_tool.core.rebuild import process_one
from labeling_tool.core.constants import CLASS_LABELS
from labeling_tool.core.mask_codec import decode_mask


def mask_name(origin_filename: str) -> str:
    """Mask filename for an origin image (Detected/Rebuilt/Labeling share it)."""
    return f"{Path(origin_filename).stem}_mask.png"


def bbox_name(origin_filename: str) -> str:
    return f"{Path(origin_filename).stem}.bbox.json"


def _rebuilt_is_fresh(rebuilt: Path, detected: Path) -> bool:
    """Rebuilt is fresh if its Detected source is gone or not newer than it."""
    if not detected.exists():
        return True
    return rebuilt.stat().st_mtime >= detected.stat().st_mtime


def resolve_display_mask(*, labeling_dir, rebuilt_dir, detected_dir,
                         origin_filename) -> tuple[Path | None, str]:
    """Pick the mask to display for an origin image.

    Returns (path, source):
      Labeling/<name> exists                  -> (path, "labeling")
      Rebuilt/<name> exists and is fresh       -> (path, "rebuilt")
      otherwise                                -> (None, "needs_rebuild")
    A None dir means that layer is unavailable.
    """
    name = mask_name(origin_filename)
    if labeling_dir is not None:
        lab = Path(labeling_dir) / name
        if lab.exists():
            return lab, "labeling"
    if rebuilt_dir is not None:
        reb = Path(rebuilt_dir) / name
        if reb.exists():
            det = Path(detected_dir) / name if detected_dir is not None else None
            if det is None or _rebuilt_is_fresh(reb, det):
                return reb, "rebuilt"
    return None, "needs_rebuild"


def build_rebuilt_label_mask(origin_bgr: np.ndarray,
                             coarse_raw: np.ndarray) -> np.ndarray:
    """Build a Rebuilt label mask: crack intensity-refined, other class kept.

    `coarse_raw` is the Detected/Labeling mask as read (3-ch BGR, integer label,
    or single-ch). It is decoded via the codec, crack is refined via process_one,
    and the non-crack (spalling) class is carried through (resized if needed).
    Returns a single-channel uint8 label image (0/1/2) with crack precedence.
    """
    crack_in, spalling_in = decode_mask(coarse_raw)
    coarse_gray = (crack_in if crack_in is not None
                   else np.zeros(coarse_raw.shape[:2], dtype=np.uint8))
    guided, _, _ = process_one(origin_bgr, coarse_gray, compute_length=False)
    out = np.zeros(guided.shape[:2], dtype=np.uint8)
    if spalling_in is not None and spalling_in.max() > 0:
        g = spalling_in
        if g.shape != guided.shape:
            g = cv2.resize(g, (guided.shape[1], guided.shape[0]),
                           interpolation=cv2.INTER_NEAREST)
        out[g > 0] = CLASS_LABELS["spalling"]
    out[guided > 0] = CLASS_LABELS["crack"]
    return out
