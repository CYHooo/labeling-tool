"""1-px stroke thinning for the brush (relocated out of the former rebuild pkg).

ImageCanvas reduces a roughly-painted crack stroke to its 1-px skeleton on
mouse release. Pure numpy / OpenCV / scikit-image (no opencv-contrib, no scipy).
"""

import numpy as np
import cv2
from skimage.morphology import skeletonize as _sk_skel


def skeletonize_mask(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Binarize (>=127) and extract a strict 1-px skeleton. Returns (bin, skel)."""
    _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    skel = (_sk_skel(bin_mask > 0).astype(np.uint8)) * 255
    return bin_mask, skel


def _neighbor_count(skel: np.ndarray) -> np.ndarray:
    """Count 8-connected skeleton neighbors at each skeleton pixel."""
    k = np.ones((3, 3), np.uint8)
    k[1, 1] = 0
    s = (skel > 0).astype(np.uint8)
    return cv2.filter2D(s, -1, k, borderType=cv2.BORDER_CONSTANT) * s


def prune_skeleton(skel: np.ndarray, min_branch: int = 20) -> np.ndarray:
    """Remove short spur branches from a 1-px skeleton (keeps the main trunk)."""
    s = (skel > 0).astype(np.uint8)
    nb = _neighbor_count(s)
    branch_pts = (nb >= 3) & (s > 0)

    seg = s.copy()
    seg[branch_pts] = 0
    n, labels = cv2.connectedComponents(seg)

    out = s.copy()
    for lab in range(1, n):
        comp = labels == lab
        if comp.sum() < min_branch and np.any((nb == 1) & comp):
            out[comp] = 0
    out[branch_pts] = 1
    return (out * 255).astype(np.uint8)


def thin_stroke_into(crack_mask: np.ndarray, stroke_mask: np.ndarray,
                     pad: int = 2, prune_min_branch: int = 0) -> None:
    """Replace a freshly-painted thick brush stroke with its 1-px skeleton.

    Operates in place on `crack_mask`, limited to the stroke's bounding box, and
    only touches the stroke region — pre-existing crack outside it is preserved.
    """
    ys, xs = np.where(stroke_mask > 0)
    if len(ys) == 0:
        return
    h, w = crack_mask.shape
    y0, y1 = max(0, int(ys.min()) - pad), min(h, int(ys.max()) + 1 + pad)
    x0, x1 = max(0, int(xs.min()) - pad), min(w, int(xs.max()) + 1 + pad)

    crop = stroke_mask[y0:y1, x0:x1]
    _, skel = skeletonize_mask(crop)
    if prune_min_branch:
        skel = prune_skeleton(skel, min_branch=prune_min_branch)

    region = crack_mask[y0:y1, x0:x1]   # view -> writes back into crack_mask
    region[crop > 0] = 0                # drop the thick stroke
    region[skel > 0] = 255             # keep the 1-px centerline
