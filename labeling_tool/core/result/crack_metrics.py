"""Per-image crack metrics: max / min / mean width, total length (mm).

Width is measured with a distance transform: at each skeleton pixel the
distance to the nearest background pixel is the half-width, so the local
width is ``2 * dist - 1`` (the ``-1`` makes a 1px line measure 1px). This is
fully vectorized — no per-skeleton-pixel Python loop — which is orders of
magnitude faster than the old normal-ray walk on long cracks / slow CPUs.

Length is measured directly on that skeleton (orthogonal + sqrt(2)*diagonal
adjacency count), avoiding the heavy gap-bridging centerline rebuild.
"""

from dataclasses import dataclass

import numpy as np
import cv2
from skimage.morphology import skeletonize


def measure_length_px(centerline: np.ndarray) -> float:
    """
    Estimate centerline length in pixels with sqrt(2) diagonal weighting.

    Counts orthogonal vs diagonal adjacencies inside the skeleton:
        length = #orthogonal_pairs + sqrt(2) * #diagonal_pairs
    """
    s = (centerline > 0).astype(np.uint8)
    ortho_k = np.array([[0, 1, 0], [1, 0, 0], [0, 0, 0]], np.uint8)
    diag_k  = np.array([[1, 0, 0], [0, 0, 0], [0, 0, 0]], np.uint8)
    ortho = float(np.sum(cv2.filter2D(s, -1, ortho_k) * s))
    diag  = float(np.sum(cv2.filter2D(s, -1, diag_k) * s))
    return ortho + diag * float(np.sqrt(2))


@dataclass
class CrackMetrics:
    max_width_mm: float | None
    min_width_mm: float | None
    mean_width_mm: float | None
    length_mm: float | None

    @classmethod
    def zero(cls) -> "CrackMetrics":
        return cls(0.0, 0.0, 0.0, 0.0)

    @classmethod
    def na(cls) -> "CrackMetrics":
        return cls(None, None, None, None)


def compute_crack_metrics(
    crack_mask: np.ndarray, scale_px_per_cm: float
) -> CrackMetrics:
    """Return crack width + length metrics in mm. Empty mask -> zero()."""
    binary = crack_mask > 0
    if not binary.any():
        return CrackMetrics.zero()
    skel = skeletonize(binary)
    if not skel.any():
        return CrackMetrics.zero()

    # Width via distance transform: distance-to-edge at the centerline is the
    # half-width; 2*dist-1 recovers the pixel width (1px line -> 1px), clamped
    # to >= 1 for any foreground skeleton pixel.
    dist = cv2.distanceTransform(binary.astype(np.uint8), cv2.DIST_L2, 5)
    widths_px = np.maximum(2.0 * dist[skel] - 1.0, 1.0)

    length_px = measure_length_px(skel.astype(np.uint8) * 255)

    cm_per_px = 1.0 / scale_px_per_cm
    mm_per_px = cm_per_px * 10.0
    return CrackMetrics(
        max_width_mm  = float(widths_px.max()) * mm_per_px,
        min_width_mm  = float(widths_px.min()) * mm_per_px,
        mean_width_mm = float(widths_px.mean()) * mm_per_px,
        length_mm     = float(length_px) * mm_per_px,
    )


def compute_spalling_area_mm2(
    spalling_mask: np.ndarray | None,
    scale_px_per_cm: float | None,
) -> float | None:
    """
    Returns mm² area; 0 when mask empty/None and scale known; None when scale
    is unknown.
    """
    if scale_px_per_cm is None:
        return None
    if spalling_mask is None:
        return 0.0
    px_count = int(np.count_nonzero(spalling_mask))
    cm_per_px = 1.0 / scale_px_per_cm
    return px_count * cm_per_px * cm_per_px * 100.0
