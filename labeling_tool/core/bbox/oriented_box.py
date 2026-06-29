"""Oriented bounding box data class + minAreaRect-based factory.

The unified `from_clicks` algorithm handles both single-line cracks (2
clicks → degenerate zero-thickness rect along the line) and complex
multi-direction cracks (N>=3 clicks → cv2.minAreaRect), then uniformly
pads all 4 sides.
"""

from dataclasses import dataclass
import math

import numpy as np
import cv2


@dataclass
class OrientedBox:
    cx: float
    cy: float
    w: float
    h: float
    angle_deg: float   # rotation in degrees; box's local x-axis points in
                       # direction (cos(a), sin(a)) in image coordinates.

    def corners(self) -> np.ndarray:
        """(4, 2) float; order TL, TR, BR, BL after rotation."""
        rad = math.radians(self.angle_deg)
        c, s = math.cos(rad), math.sin(rad)
        hw, hh = self.w / 2, self.h / 2
        loc = np.array(
            [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]],
            dtype=np.float32,
        )
        rot = np.array([[c, -s], [s, c]], dtype=np.float32)
        return (loc @ rot.T) + np.array([self.cx, self.cy], dtype=np.float32)

    def handles(self, rot_offset_px: float = 30.0) -> dict:
        """9 handles in image coords. Keys: tl,t,tr,r,br,b,bl,l,rot.

        rot_offset_px: distance from the top edge midpoint to the rotation
        grip, measured in IMAGE pixels. Caller is expected to pass
        (desired_widget_px / viewport.scale) so the grip stays at a
        constant on-screen distance from the box regardless of zoom.
        """
        cor = self.corners()
        tl, tr, br, bl = cor
        t = (tl + tr) / 2
        r = (tr + br) / 2
        b = (br + bl) / 2
        l = (bl + tl) / 2
        rad = math.radians(self.angle_deg)
        # "up" in image coords is the negative-y direction in box local frame
        up = np.array([math.sin(rad), -math.cos(rad)]) * float(rot_offset_px)
        rot = t + up
        return {
            "tl": tuple(tl), "tr": tuple(tr), "br": tuple(br), "bl": tuple(bl),
            "t": tuple(t), "r": tuple(r), "b": tuple(b), "l": tuple(l),
            "rot": tuple(rot),
        }

    def contains(self, ix: float, iy: float) -> bool:
        """Point-in-rotated-rect test."""
        return cv2.pointPolygonTest(
            self.corners().astype(np.float32), (float(ix), float(iy)), False,
        ) >= 0

    def hit_test_handle(self, ix: float, iy: float,
                        tol_px: float = 10.0,
                        rot_offset_px: float = 30.0) -> str | None:
        for name, (hx, hy) in self.handles(rot_offset_px=rot_offset_px).items():
            if (hx - ix) ** 2 + (hy - iy) ** 2 <= tol_px ** 2:
                return name
        return None

    def area_px2(self) -> float:
        return float(self.w * self.h)

    @classmethod
    def from_clicks(cls, clicks, padding_px: float) -> "OrientedBox":
        """
        Unified algorithm for both single-line and complex cracks.

        N=2: build a zero-thickness line-aligned rect manually (avoids
             OpenCV's unstable handling of degenerate minAreaRect).
        N>=3: cv2.minAreaRect.
        Then pad all 4 sides by padding_px.
        """
        if len(clicks) < 2:
            raise ValueError("need at least 2 clicks")
        pts = np.array(clicks, dtype=np.float32)
        if len(pts) == 2:
            p0, p1 = pts
            dx, dy = float(p1[0] - p0[0]), float(p1[1] - p0[1])
            length = math.hypot(dx, dy)
            angle = math.degrees(math.atan2(dy, dx))
            cx, cy = (p0 + p1) / 2
            w0, h0 = length, 0.0
        else:
            (cx, cy), (w0, h0), angle = cv2.minAreaRect(pts)
        return cls(
            cx=float(cx), cy=float(cy),
            w=float(w0) + 2 * padding_px,
            h=float(h0) + 2 * padding_px,
            angle_deg=float(angle),
        )


def union_area_px2(boxes: list["OrientedBox"]) -> float:
    """Area (px^2) of the UNION of the given oriented boxes.

    Overlapping regions are counted ONCE (not summed). Every box is rasterized
    onto a tight binary canvas (the bounding region of all corners) and the
    covered pixels are counted, so rotation and arbitrary overlap are handled
    exactly at pixel resolution. Returns 0.0 for an empty list.
    """
    if not boxes:
        return 0.0
    corners = [b.corners() for b in boxes]
    pts = np.vstack(corners)
    x0 = int(np.floor(pts[:, 0].min()))
    y0 = int(np.floor(pts[:, 1].min()))
    x1 = int(np.ceil(pts[:, 0].max()))
    y1 = int(np.ceil(pts[:, 1].max()))
    w, h = x1 - x0 + 1, y1 - y0 + 1
    if w <= 0 or h <= 0:
        return 0.0
    canvas = np.zeros((h, w), dtype=np.uint8)
    origin = np.array([x0, y0], dtype=np.float32)
    for c in corners:
        poly = np.round(c - origin).astype(np.int32)
        cv2.fillConvexPoly(canvas, poly, 1)
    return float(np.count_nonzero(canvas))


def bboxes_from_contours(contours, min_area_px: float = 1.0) -> list["OrientedBox"]:
    """Fit one OrientedBox to each contour via cv2.minAreaRect.

    Used to auto-generate repair bboxes from the 15cm (repair15) outer contours.
    No padding is added — the 15cm expansion is already baked into the mask.
    Degenerate contours (<3 points, zero/sub-min area) are skipped.
    """
    out: list[OrientedBox] = []
    for c in contours or []:
        pts = np.asarray(c, dtype=np.float32).reshape(-1, 2)
        if len(pts) < 3:
            continue
        (cx, cy), (w, h), angle = cv2.minAreaRect(pts)
        if w <= 0 or h <= 0 or (w * h) < min_area_px:
            continue
        out.append(OrientedBox(cx=float(cx), cy=float(cy),
                               w=float(w), h=float(h), angle_deg=float(angle)))
    return out
