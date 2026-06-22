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
    scale_points: list | None = None,
) -> None:
    """Overwrite the JSON file. Empty list is still written.

    scale_points: the two manual-measurement points (image coords) so a manual
    scale's line can be redrawn on revisit; [] for ArUco/none.
    """
    payload = {
        "image": image_filename,
        "scale_px_per_cm": scale_px_per_cm,
        "scale_source": scale_source,
        "scale_points": [[float(x), float(y)] for x, y in (scale_points or [])],
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


def load_scale_info(path: Path) -> dict:
    """Return {"scale": float|None, "source": str, "points": [(x,y), ...]}.

    Used on image load to honor a saved MANUAL scale (so ArUco doesn't override
    it) and to redraw its measurement line.
    """
    empty = {"scale": None, "source": "none", "points": []}
    if path is None or not path.exists():
        return empty
    data = json.loads(path.read_text(encoding="utf-8"))
    s = data.get("scale_px_per_cm")
    s = float(s) if s is not None and float(s) > 0 else None
    pts = [(float(p[0]), float(p[1]))
           for p in data.get("scale_points", []) if len(p) == 2]
    return {"scale": s, "source": data.get("scale_source", "none"), "points": pts}
