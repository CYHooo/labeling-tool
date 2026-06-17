"""Derived masks for the local Photo Viewer: 균열 하이라이트 + 15cm 경계.

Pure functions (no Qt, no I/O). Generated at save time from the in-memory
crack/spalling layers, written to HighLight/ and Repair15/, and uploaded
to S3 as high_{ts}.png / 15_{ts}.png.
"""

from __future__ import annotations

import cv2
import numpy as np

from labeling_tool.core.constants import CLASS_LABELS

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


def build_highlight(crack: np.ndarray | None,
                    spalling: np.ndarray | None) -> np.ndarray:
    """Dilate each class by 10px and re-encode to a single-channel 0/1/2 mask.

    spalling (2) is written first, then crack (1) overwrites it -> crack
    precedence on overlap. Raises ValueError when both layers are None.
    """
    cb = _binary(crack)
    sb = _binary(spalling)
    if cb is None and sb is None:
        raise ValueError("build_highlight requires at least one of crack/spalling")

    shape = cb.shape if cb is not None else sb.shape
    out = np.zeros(shape, dtype=np.uint8)
    kernel = _ellipse_kernel(_HIGHLIGHT_DILATE_PX)

    if sb is not None:
        grown = cv2.dilate(sb, kernel)
        out[grown > 0] = CLASS_LABELS["spalling"]
    if cb is not None:
        grown = cv2.dilate(cb, kernel)
        out[grown > 0] = CLASS_LABELS["crack"]   # crack precedence
    return out


def build_repair15(crack: np.ndarray | None,
                   spalling: np.ndarray | None,
                   px_per_cm: float) -> np.ndarray:
    """Foreground union expanded by round(15*px_per_cm) px, FILLED 0/255.

    Uses a distance transform (O(N), Euclidean) instead of a giant dilation
    kernel, so it stays fast even at large px/cm. Raises ValueError when both
    layers are None.
    """
    cb = _binary(crack)
    sb = _binary(spalling)
    if cb is None and sb is None:
        raise ValueError("build_repair15 requires at least one of crack/spalling")

    shape = cb.shape if cb is not None else sb.shape
    union = np.zeros(shape, dtype=np.uint8)
    if cb is not None:
        union |= cb
    if sb is not None:
        union |= sb
    if int(union.max()) == 0:
        return np.zeros(shape, dtype=np.uint8)

    pad_px = int(round(_REPAIR15_CM * float(px_per_cm)))
    # distance from each pixel to the nearest foreground pixel
    src = np.where(union > 0, np.uint8(0), np.uint8(255))
    dist = cv2.distanceTransform(src, cv2.DIST_L2, 5)
    return np.where(dist <= pad_px, np.uint8(255), np.uint8(0)).astype(np.uint8)


def generate_derived_masks(crack: np.ndarray | None,
                           spalling: np.ndarray | None,
                           px_per_cm: float,
                           highlight_path,
                           repair15_path
                           ) -> tuple[np.ndarray, np.ndarray | None]:
    """Build the highlight (+ scale-dependent repair15) and write them to disk.

    Returns (highlight, repair15_or_None). repair15 is built+written only when
    px_per_cm is truthy. A None path skips the write but the array is still
    returned (so the canvas can refresh). Callers ensure parent dirs exist.
    """
    highlight = build_highlight(crack, spalling)
    if highlight_path is not None:
        cv2.imwrite(str(highlight_path), highlight)
    repair15 = None
    if px_per_cm:
        repair15 = build_repair15(crack, spalling, px_per_cm)
        if repair15_path is not None:
            cv2.imwrite(str(repair15_path), repair15)
    return highlight, repair15
