"""Continuous centerline construction and length measurement.

The 'guided' mask from width_fit is jagged and 1-2 px wide; thinning it
directly shatters into many segments. For length measurement we instead
work from the original COARSE annotation (still continuous), and use a
multi-step pipeline that bridges small gaps.
"""

import numpy as np
import cv2
from skimage.morphology import skeletonize as _sk_skel

from labeling_tool.core.rebuild.thinning import prune_skeleton, connect_gaps


def build_length_centerline(
    coarse_mask: np.ndarray,
    min_area: int = 200,
    min_branch: int = 25,
    gap_max: int = 35,
) -> np.ndarray:
    """
    Pipeline: drop tiny blobs -> skimage skeletonize -> prune spurs ->
    drop tiny skeleton fragments -> bridge small gaps.

    Returns a connected (or near-connected) 1-px centerline mask (0/255).
    """
    _, b = cv2.threshold(coarse_mask, 127, 255, cv2.THRESH_BINARY)

    # 1) Remove tiny disconnected blobs.
    n, lab, stats, _ = cv2.connectedComponentsWithStats(b)
    big = np.zeros_like(b)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            big[lab == i] = 255

    # 2) Strict 1-px skeleton + spur prune.
    skel = (_sk_skel(big > 0).astype(np.uint8)) * 255
    skel = prune_skeleton(skel, min_branch=min_branch)

    # 3) Drop short leftover fragments.
    n2, lab2 = cv2.connectedComponents((skel > 0).astype(np.uint8))
    clean = np.zeros_like(skel)
    for i in range(1, n2):
        if np.count_nonzero(lab2 == i) >= min_branch:
            clean[lab2 == i] = 255

    # 4) Bridge small real gaps.
    return connect_gaps(clean, gap_max=gap_max)


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
