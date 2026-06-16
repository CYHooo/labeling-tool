"""End-to-end rebuild pipeline: image + coarse mask -> width-fit + centerline."""

import numpy as np

from labeling_tool.core.rebuild.thinning import skeletonize_mask
from labeling_tool.core.rebuild.width_fit import rebuild_intensity_guided
from labeling_tool.core.rebuild.length_centerline import (
    build_length_centerline, measure_length_px,
)


REF_SIZE = 4032
_BASE = {
    "search_radius": 8,   # length-like
    "block_size":    51,  # length-like (odd)
    "min_area":      200, # area-like
    "min_branch":    25,  # length-like
    "gap_max":       35,  # length-like
}


def autoscale_params(img_shape) -> dict:
    """
    Scale pixel parameters proportionally to image long side so the pipeline
    behaves consistently across resolutions (tuned at REF_SIZE).

    Length-like params scale linearly; area-like (min_area) scales with the
    square of the linear ratio.
    """
    h, w = img_shape[:2]
    scale = max(h, w) / REF_SIZE
    bs = max(11, round(_BASE["block_size"] * scale))
    if bs % 2 == 0:
        bs += 1
    return {
        "search_radius": max(2, round(_BASE["search_radius"] * scale)),
        "block_size":    bs,
        "min_area":      max(50, round(_BASE["min_area"] * scale * scale)),
        "min_branch":    max(8,  round(_BASE["min_branch"] * scale)),
        "gap_max":       max(10, round(_BASE["gap_max"] * scale)),
    }


def process_one(
    img: np.ndarray, coarse_mask: np.ndarray,
    search_radius: int | None = None, block_size: int | None = None, C: int = 8,
    min_area: int | None = None, min_branch: int | None = None,
    gap_max: int | None = None, compute_length: bool = True,
) -> tuple[np.ndarray, np.ndarray | None, float]:
    """
    Returns:
        guided_mask: width-fitted crack mask (0/255), clipped to coarse.
        centerline:  continuous 1-px centerline (0/255), or None if
                     compute_length=False.
        length_px:   centerline length in pixels (0.0 if not computed).

    compute_length=False skips the (expensive) gap-bridged centerline + length,
    which every caller that only needs `guided` (Rebuilt cache prebuild, on-load
    rebuild) discards anyway — roughly a third of the per-image cost.
    """
    import cv2
    if coarse_mask.shape[:2] != img.shape[:2]:
        coarse_mask = cv2.resize(
            coarse_mask, (img.shape[1], img.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )

    auto = autoscale_params(img.shape)
    sr = auto["search_radius"] if search_radius is None else search_radius
    bs = auto["block_size"]    if block_size    is None else block_size
    ma = auto["min_area"]      if min_area      is None else min_area
    mb = auto["min_branch"]    if min_branch    is None else min_branch
    gm = auto["gap_max"]       if gap_max       is None else gap_max

    bin_mask, coarse_skel = skeletonize_mask(coarse_mask)
    guided = rebuild_intensity_guided(
        img, coarse_skel, bin_mask,
        search_radius=sr, block_size=bs, C=C, clip_to_coarse=True,
    )
    if not compute_length:
        return guided, None, 0.0
    centerline = build_length_centerline(
        coarse_mask, min_area=ma, min_branch=mb, gap_max=gm,
    )
    length = measure_length_px(centerline)
    return guided, centerline, length
