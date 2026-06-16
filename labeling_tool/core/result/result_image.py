"""Generate Result/<stem>.png — opaque masks + semi-transparent bbox overlay.

Layers (bottom -> top):
    1. Original BGR
    2. crack_mask>0 pixels  -> BGR(0,0,255) red, opaque
    3. spalling_mask>0 px   -> BGR(0,255,0) green, opaque
    4. bbox polygons        -> BGR(0,165,255) orange, ~20% opacity
"""

from pathlib import Path

import numpy as np
import cv2

from labeling_tool.core.bbox.oriented_box import OrientedBox


_CRACK_BGR    = (0, 0, 255)
_SPALLING_BGR = (0, 255, 0)
_BBOX_BGR     = (0, 165, 255)
_BBOX_ALPHA   = 0.20


def write_result_image(
    out_path: Path, origin_bgr: np.ndarray,
    crack_mask: np.ndarray | None,
    spalling_mask: np.ndarray | None,
    boxes: list[OrientedBox],
) -> None:
    """Composite layers and write a PNG file."""
    out = origin_bgr.copy()
    if crack_mask is not None:
        out[crack_mask > 0] = _CRACK_BGR
    if spalling_mask is not None:
        out[spalling_mask > 0] = _SPALLING_BGR

    if boxes:
        overlay = out.copy()
        for b in boxes:
            poly = b.corners().astype(np.int32)
            cv2.fillPoly(overlay, [poly], _BBOX_BGR)
        out = cv2.addWeighted(out, 1.0 - _BBOX_ALPHA, overlay, _BBOX_ALPHA, 0.0)

    cv2.imwrite(str(out_path), out)
