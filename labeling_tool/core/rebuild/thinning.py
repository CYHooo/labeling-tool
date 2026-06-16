"""Skeleton extraction, spur pruning, and gap bridging.

Pure-numpy / OpenCV / scikit-image implementations. Does not depend on
opencv-contrib-python (no cv2.ximgproc) or scipy (no cdist).
"""

import numpy as np
import cv2
from skimage.morphology import skeletonize as _sk_skel


def skeletonize_mask(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Binarize a mask (>=127 = foreground) and extract a strict 1-px skeleton.

    Returns:
        bin_mask: cleaned binary mask (0/255).
        skeleton: 1-px skeleton (0/255).
    """
    _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    skel = (_sk_skel(bin_mask > 0).astype(np.uint8)) * 255
    return bin_mask, skel


def thin_stroke_into(crack_mask: np.ndarray, stroke_mask: np.ndarray,
                     pad: int = 2, prune_min_branch: int = 0) -> None:
    """Replace a freshly-painted thick brush stroke with its 1-px skeleton.

    Coarse-annotation workflow: the user roughly paints a crack at eye-visible
    thickness; on mouse release we reduce just that stroke to a 1-px centerline
    (never wider than the real crack), keeping only position/shape. Operates
    in place on `crack_mask`, limited to the stroke's bounding box so it stays
    fast on large panoramas, and only touches the stroke region — pre-existing
    crack outside the stroke is preserved.
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


def _neighbor_count(skel: np.ndarray) -> np.ndarray:
    """Count 8-connected skeleton neighbors at each skeleton pixel."""
    k = np.ones((3, 3), np.uint8)
    k[1, 1] = 0
    s = (skel > 0).astype(np.uint8)
    return cv2.filter2D(s, -1, k, borderType=cv2.BORDER_CONSTANT) * s


def prune_skeleton(skel: np.ndarray, min_branch: int = 20) -> np.ndarray:
    """
    Remove short spur branches from a 1-px skeleton.

    Branch points (>=3 neighbors) are temporarily removed to split the
    skeleton into segments; any segment shorter than min_branch that
    contains an endpoint (a 1-neighbor tip, i.e. a dangling spur) is
    dropped. Branch points are restored afterwards so the main trunk
    stays connected.
    """
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


def connect_gaps(skel: np.ndarray, gap_max: int = 35,
                 max_iter: int = 80) -> np.ndarray:
    """
    Close small breaks in a 1-px skeleton by joining the nearest endpoints
    of DIFFERENT segments with a straight line, greedily, shortest first.

    Only gaps <= gap_max are bridged, so real crack tips (far apart) stay
    open and separate branches are not wrongly merged.

    Pure-numpy pairwise distances (no scipy).
    """
    s = (skel > 0).astype(np.uint8) * 255
    k = np.ones((3, 3), np.uint8); k[1, 1] = 0
    for _ in range(max_iter):
        n, lab = cv2.connectedComponents((s > 0).astype(np.uint8))
        if n - 1 <= 1:
            break
        sb = (s > 0).astype(np.uint8)
        nb = cv2.filter2D(sb, -1, k) * sb
        eys, exs = np.where(nb == 1)
        if len(eys) < 2:
            break
        pts = np.column_stack([eys, exs]).astype(np.float32)
        plab = lab[eys, exs]
        diff = pts[:, None, :] - pts[None, :, :]
        D = np.sqrt((diff ** 2).sum(-1))
        same = plab[:, None] == plab[None, :]
        D[same] = np.inf
        idx = int(np.argmin(D))
        i, j = divmod(idx, len(pts))
        if D[i, j] > gap_max:
            break
        cv2.line(s, (exs[i], eys[i]), (exs[j], eys[j]), 255, 1)
    return s
