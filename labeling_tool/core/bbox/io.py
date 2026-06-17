"""JSON serialization for bbox annotations.

Format example:
    {
      "image": "DSC_1234.jpg",
      "scale_px_per_cm": 52.30,
      "scale_source": "aruco",
      "boxes": [
        {"cx": 1234.5, "cy": 567.8, "w": 800.0, "h": 200.0, "angle_deg": 23.5}
      ]
    }
"""

import json
from pathlib import Path

from labeling_tool.core.bbox.oriented_box import OrientedBox


def save_bboxes(
    path: Path, image_filename: str,
    boxes: list[OrientedBox],
    scale_px_per_cm: float | None,
    scale_source: str,
) -> None:
    """Overwrite the JSON file. Empty list is still written."""
    payload = {
        "image": image_filename,
        "scale_px_per_cm": scale_px_per_cm,
        "scale_source": scale_source,
        "boxes": [
            {
                "cx": b.cx, "cy": b.cy,
                "w": b.w, "h": b.h,
                "angle_deg": b.angle_deg,
            }
            for b in boxes
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_bboxes(path: Path) -> list[OrientedBox]:
    """Return [] if file missing or empty boxes list."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [OrientedBox(**d) for d in data.get("boxes", [])]


def load_scale(path: Path) -> float | None:
    """Return the px/cm scale persisted alongside the bboxes, or None.

    The scale is what the tool actually measured for that image (ArUco
    auto-detection, or manual measurement as a fallback) at save time, so
    uploads use the tool's effective scale rather than a stale server value.
    """
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    s = data.get("scale_px_per_cm")
    if s is None:
        return None
    s = float(s)
    return s if s > 0 else None
