"""High-level entry: gather metrics + write image + write txt."""

from pathlib import Path

import numpy as np

from labeling_tool.core.bbox.oriented_box import OrientedBox
from labeling_tool.core.result.crack_metrics import (
    CrackMetrics, compute_crack_metrics, compute_spalling_area_mm2,
)
from labeling_tool.core.result.text_report import write_text_report
from labeling_tool.core.result.result_image import write_result_image


def export_result(
    out_dir: Path, image_filename: str,
    origin_bgr: np.ndarray,
    crack_mask: np.ndarray | None,
    spalling_mask: np.ndarray | None,
    boxes: list[OrientedBox],
    scale_px_per_cm: float | None,
) -> None:
    """
    Side effects: writes <out_dir>/<stem>.png + <out_dir>/<stem>.txt.

    Behavior matrix:
        scale=None              -> all mm-typed fields are 'n/a' in txt
        crack_mask=None         -> CrackMetrics.zero() (or .na() if scale=None)
        crack_mask is all zero  -> CrackMetrics.zero()
        spalling_mask=None      -> spalling_area_mm2 = 0.0 (scale known)
                                                       n/a  (scale unknown)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(image_filename).stem

    if scale_px_per_cm is None:
        metrics = CrackMetrics.na()
    elif crack_mask is None:
        metrics = CrackMetrics.zero()
    else:
        metrics = compute_crack_metrics(crack_mask, scale_px_per_cm)

    spalling_area_mm2 = compute_spalling_area_mm2(spalling_mask, scale_px_per_cm)

    write_text_report(
        out_dir / f"{stem}.txt",
        image_filename, scale_px_per_cm, metrics,
        spalling_area_mm2, boxes,
    )
    write_result_image(
        out_dir / f"{stem}.png",
        origin_bgr, crack_mask, spalling_mask, boxes,
    )
