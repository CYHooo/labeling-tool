"""Mask overlay rendering for ImageCanvas.

Pure function (no class state): given a painter, viewport, widget size,
and the two mask layers, draws semi-transparent red/green overlays for
crack/spalling channels respectively.
"""

import numpy as np
import cv2
from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QPainter, QImage

from labeling_tool.core.canvas.viewport import Viewport


# RGB tuples for each mask channel
_CRACK_RGB    = (255,  60,  60)
_SPALLING_RGB = ( 60, 230,  60)

# Minimum on-screen crack-line thickness (DISPLAY ONLY). 1px stored lines are
# nearly invisible when zoomed out; we thicken the SCREEN-space overlay so the
# stored mask — and the width metrics computed from it — stay 1px.
DISPLAY_LINE_PX = 3


def _screen_thicken(binimg: np.ndarray, target_px: int = DISPLAY_LINE_PX) -> np.ndarray:
    """Dilate a screen-space binary overlay to a minimum on-screen thickness.

    Cheap and zoom-independent: it runs on the already-resized (widget-sized)
    image with a tiny fixed kernel, unlike an image-space dilate whose kernel
    blew up (and cost 80+ ms/frame) when zoomed out on a big panorama.
    """
    r = max(0, (int(target_px) - 1) // 2)
    if r <= 0:
        return binimg
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(binimg, k)


def paint_mask_overlay(
    painter: QPainter,
    viewport: Viewport,
    widget_w: int,
    widget_h: int,
    crack_mask: np.ndarray | None,
    spalling_mask: np.ndarray | None,
) -> None:
    """Render both mask channels as semi-transparent overlays."""
    if viewport.scale <= 0:
        return
    ih, iw = viewport.img_h, viewport.img_w
    scale = viewport.scale
    ox, oy = viewport.offset.x(), viewport.offset.y()

    x0 = max(0, int((0 - ox) / scale))
    y0 = max(0, int((0 - oy) / scale))
    x1 = min(iw, int(np.ceil((widget_w - ox) / scale)) + 1)
    y1 = min(ih, int(np.ceil((widget_h - oy) / scale)) + 1)
    if x1 <= x0 or y1 <= y0:
        return

    cw, ch = (x1 - x0), (y1 - y0)
    wsw = max(1, int(cw * scale))
    wsh = max(1, int(ch * scale))
    px = int(ox + x0 * scale)
    py = int(oy + y0 * scale)

    for mask, rgb in (
        (crack_mask,    _CRACK_RGB),
        (spalling_mask, _SPALLING_RGB),
    ):
        if mask is None:
            continue
        crop = mask[y0:y1, x0:x1]
        if crop.max() == 0:
            continue
        # Resize to screen FIRST so all further work is bounded by widget size.
        # INTER_AREA when shrinking keeps thin (1px) lines from being dropped;
        # INTER_NEAREST when enlarging.
        shrinking = (wsw < cw) or (wsh < ch)
        interp = cv2.INTER_AREA if shrinking else cv2.INTER_NEAREST
        resized = cv2.resize(crop, (wsw, wsh), interpolation=interp)
        binimg = np.where(resized > 0, np.uint8(255), np.uint8(0))
        # Display-only minimum thickness; never touches the stored mask.
        binimg = _screen_thicken(binimg)
        rgba = np.zeros((wsh, wsw, 4), dtype=np.uint8)
        rgba[..., 0] = rgb[2]
        rgba[..., 1] = rgb[1]
        rgba[..., 2] = rgb[0]
        rgba[..., 3] = (binimg.astype(np.float32) * 0.5).astype(np.uint8)
        qimg = QImage(rgba.data, wsw, wsh, wsw * 4, QImage.Format_RGBA8888)
        painter.drawImage(QPointF(px, py), qimg)
