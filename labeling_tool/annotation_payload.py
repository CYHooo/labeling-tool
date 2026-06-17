"""Build a register-annotations `item` dict from local edit state.

Maps the labeling tool's internal artifacts (crack/spalling masks,
OrientedBox repair areas, ArUco scale) onto the register-annotations schema documented in
api-reference_v1.0.7 (로컬 포토뷰어 API).
"""

from __future__ import annotations

import numpy as np

from labeling_tool.core.bbox.oriented_box import OrientedBox
from labeling_tool.core.result.crack_metrics import (
    compute_crack_metrics, compute_spalling_area_mm2,
)


def _defect_type(has_crack: bool, has_spalling: bool) -> int:
    """0 crack, 1 spalling(박리), 2 mixed(혼합). Default 0 when neither."""
    if has_crack and has_spalling:
        return 2
    if has_spalling:
        return 1
    return 0


def build_annotation_item(
    *,
    timestamp: int,
    mask_s3_key: str,
    px_per_cm: float,
    scale_source: str,
    crack_mask: np.ndarray | None,
    spalling_mask: np.ndarray | None,
    boxes: list[OrientedBox],
) -> dict:
    mm_per_px = 10.0 / px_per_cm
    px_per_mm = px_per_cm / 10.0

    has_crack = crack_mask is not None and bool((crack_mask > 0).any())
    has_spalling = spalling_mask is not None and bool((spalling_mask > 0).any())

    if has_crack:
        cm = compute_crack_metrics(crack_mask, px_per_cm)
    else:
        from labeling_tool.core.result.crack_metrics import CrackMetrics
        cm = CrackMetrics.zero()

    spalling_mm2 = compute_spalling_area_mm2(spalling_mask, px_per_cm) or 0.0

    bbox_area_mm2 = sum(b.area_px2() for b in boxes) * (mm_per_px ** 2)
    bbox_count = len(boxes)

    repair_areas = [
        {"cx": b.cx, "cy": b.cy, "w": b.w, "h": b.h, "angleDeg": b.angle_deg}
        for b in boxes
    ]

    crack_metrics = {
        "lengthMm": float(cm.length_mm or 0.0),
        "avgWidthMm": float(cm.mean_width_mm or 0.0),
        "minWidthMm": float(cm.min_width_mm or 0.0),
        "maxWidthMm": float(cm.max_width_mm or 0.0),
        "bboxAreaMm2": float(bbox_area_mm2),
        "bboxCount": int(bbox_count),
        "spallingMm2": float(spalling_mm2),
        "defectType": _defect_type(has_crack, has_spalling),
        "pxPerMm": float(px_per_mm),
    }

    return {
        "timestamp": int(timestamp),
        "maskS3Key": mask_s3_key,
        "pxPerCm": float(px_per_cm),
        "scaleSource": scale_source or "aruco",
        "repairAreas": repair_areas,
        "crackMetrics": crack_metrics,
    }
