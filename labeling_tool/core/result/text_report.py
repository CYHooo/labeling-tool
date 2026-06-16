"""Generate the Result/<stem>.txt metrics file."""

from pathlib import Path

from labeling_tool.core.result.crack_metrics import CrackMetrics
from labeling_tool.core.bbox.oriented_box import OrientedBox


def _fmt(v: float | None, prec: int = 2) -> str:
    return "n/a" if v is None else f"{v:.{prec}f}"


def write_text_report(
    out_path: Path, image_filename: str,
    scale_px_per_cm: float | None,
    metrics: CrackMetrics,
    spalling_area_mm2: float | None,
    boxes: list[OrientedBox],
) -> None:
    """Write the fixed-format report. Overwrites if exists."""
    if scale_px_per_cm is not None:
        cm_per_px = 1.0 / scale_px_per_cm
        bbox_total_mm2 = sum(
            b.area_px2() * cm_per_px * cm_per_px * 100.0 for b in boxes
        )
    else:
        bbox_total_mm2 = None

    lines = [
        f"image: {image_filename}",
        f"scale_px_per_cm: {_fmt(scale_px_per_cm)}",
        f"max_crack_width_mm: {_fmt(metrics.max_width_mm)}",
        f"mean_crack_width_mm: {_fmt(metrics.mean_width_mm)}",
        f"crack_length_mm: {_fmt(metrics.length_mm)}",
        f"spalling_area_mm2: {_fmt(spalling_area_mm2)}",
        f"bbox_count: {len(boxes)}",
        f"bbox_total_area_mm2: {_fmt(bbox_total_mm2)}",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
