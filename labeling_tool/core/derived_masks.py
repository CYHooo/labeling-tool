"""Derived masks for the local Photo Viewer: 균열 하이라이트 + 15cm 경계.

Pure functions (no Qt, no I/O). Generated at save time from the in-memory
class layers, written to HighLight/ and Repair15/, and uploaded
to S3 as high_{ts}.png / 15_{ts}.png.
"""

from __future__ import annotations

import cv2
import numpy as np

from labeling_tool.core.classes import CRACK_ID, SPALLING_ID

# Highlight: every class region grows by this many px so the defect reads
# clearly on the web viewer. Ellipse kernel of radius 10 (21x21).
_HIGHLIGHT_DILATE_PX = 10
# Repair15: the foreground union is padded by 15 cm worth of pixels.
_REPAIR15_CM = 15.0


def _ellipse_kernel(radius_px: int) -> np.ndarray:
    r = max(1, int(radius_px))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def _binary(layer: np.ndarray | None) -> np.ndarray | None:
    if layer is None:
        return None
    return (layer > 0).astype(np.uint8)


def _present(layers: dict) -> dict:
    out = {cid: _binary(m) for cid, m in layers.items() if m is not None}
    if not out:
        raise ValueError("derived masks need at least one class layer")
    return out


def build_highlight_layers(layers: dict) -> np.ndarray:
    """Dilate every class by 10 px and re-encode with the mask's own values
    (area classes in id order, crack last -> crack precedence)."""
    present = _present(layers)
    shape = next(iter(present.values())).shape
    out = np.zeros(shape, dtype=np.uint8)
    kernel = _ellipse_kernel(_HIGHLIGHT_DILATE_PX)
    for cid in sorted(c for c in present if c != CRACK_ID) + (
            [CRACK_ID] if CRACK_ID in present else []):
        if present[cid].any():
            out[cv2.dilate(present[cid], kernel) > 0] = cid
    return out


def build_repair15_layers(layers: dict, px_per_cm: float) -> np.ndarray:
    """Union of every class expanded by round(15*px_per_cm) px, FILLED 0/255.

    Uses a distance transform (O(N), Euclidean) instead of a giant dilation
    kernel, so it stays fast even at large px/cm."""
    present = _present(layers)
    shape = next(iter(present.values())).shape
    union = np.zeros(shape, dtype=np.uint8)
    for m in present.values():
        union |= m
    if int(union.max()) == 0:
        return np.zeros(shape, dtype=np.uint8)
    pad_px = int(round(_REPAIR15_CM * float(px_per_cm)))
    src = np.where(union > 0, np.uint8(0), np.uint8(255))
    dist = cv2.distanceTransform(src, cv2.DIST_L2, 5)
    return np.where(dist <= pad_px, np.uint8(255), np.uint8(0)).astype(np.uint8)


def generate_derived_layers(layers: dict, px_per_cm: float,
                            highlight_path, repair15_path
                            ) -> tuple[np.ndarray, np.ndarray | None]:
    """Build the highlight (+ scale-dependent repair15) and write them to disk.

    repair15 is built+written only when px_per_cm is truthy. A None path skips
    the write but the array is still returned. Callers ensure parent dirs."""
    highlight = build_highlight_layers(layers)
    if highlight_path is not None:
        cv2.imwrite(str(highlight_path), highlight)
    repair15 = None
    if px_per_cm:
        repair15 = build_repair15_layers(layers, px_per_cm)
        if repair15_path is not None:
            cv2.imwrite(str(repair15_path), repair15)
    return highlight, repair15


# Two-layer forms kept for existing callers and tests.
def build_highlight(crack, spalling) -> np.ndarray:
    if crack is None and spalling is None:
        raise ValueError("build_highlight requires at least one of crack/spalling")
    return build_highlight_layers({CRACK_ID: crack, SPALLING_ID: spalling})


def build_repair15(crack, spalling, px_per_cm: float) -> np.ndarray:
    if crack is None and spalling is None:
        raise ValueError("build_repair15 requires at least one of crack/spalling")
    return build_repair15_layers({CRACK_ID: crack, SPALLING_ID: spalling}, px_per_cm)


def generate_derived_masks(crack, spalling, px_per_cm: float,
                           highlight_path, repair15_path):
    return generate_derived_layers({CRACK_ID: crack, SPALLING_ID: spalling},
                                   px_per_cm, highlight_path, repair15_path)
