"""Intensity-guided crack width fitting.

Refines a coarse (AI-detected) crack mask down to the actual dark pixels
in the original image, restricted to a band around the coarse mask, and
clipped back to the coarse boundary.
"""

import numpy as np
import cv2


def rebuild_intensity_guided(
    img: np.ndarray,
    skeleton: np.ndarray,
    bin_mask: np.ndarray,
    search_radius: int = 8,
    block_size: int = 51,
    C: int = 8,
    clip_to_coarse: bool = True,
) -> np.ndarray:
    """
    Args:
        img: source BGR image.
        skeleton: 1-px skeleton (0/255), used as the seed connectivity anchor.
        bin_mask: binarized coarse mask (0/255), used to bound the search region.
        search_radius: how far (px) around the coarse mask to look for dark
            crack pixels.
        block_size: adaptive-threshold neighborhood (odd).
        C: adaptive-threshold offset. Higher -> stricter.
        clip_to_coarse: if True, forbid the result from extending beyond the
            coarse annotation.

    Returns:
        Rebuilt binary mask (0/255).
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Cracks are local dark valleys -> THRESH_BINARY_INV picks them out.
    dark = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, block_size, C,
    )

    # Restrict to a band around the coarse mask so unrelated dark regions
    # (shadows, markers, cables) are excluded.
    band_k = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (2 * search_radius + 1, 2 * search_radius + 1),
    )
    roi = cv2.dilate(bin_mask, band_k)
    dark = cv2.bitwise_and(dark, roi)

    # Ensure the centerline itself is always present, then bridge tiny gaps.
    dark = cv2.bitwise_or(dark, skeleton)
    dark = cv2.morphologyEx(
        dark, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    )

    # Keep only connected components that overlap the skeleton.
    _, labels = cv2.connectedComponents(dark)
    keep_labels = np.unique(labels[skeleton > 0])
    keep_labels = keep_labels[keep_labels != 0]
    result = np.isin(labels, keep_labels).astype(np.uint8) * 255

    if clip_to_coarse:
        result = cv2.bitwise_and(result, bin_mask)
    return result
