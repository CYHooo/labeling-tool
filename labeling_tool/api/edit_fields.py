"""Field names and limits of the photo-edit additions to the Viewer API
(surface per photo, surface updates and deletes in register-annotations).

Kept in one place: the server document was still on its way when this was
written, so a renamed field or a different limit is a one-line change here.
"""

from __future__ import annotations

import math

SURFACES = ("floor", "wall", "ceiling")

SURFACE_UPDATES_KEY = "surfaceUpdates"
DELETES_KEY = "deletes"
DELETED_KEY = "deleted"
SKIPPED_KEY = "skipped"

# Most surfaceUpdates / deletes entries in one register-annotations call.
EDIT_LIST_LIMIT = 100


def normalize_surface(value) -> str | None:
    """A known surface, or None for unknown / missing values."""
    return value if isinstance(value, str) and value in SURFACES else None


def _float_or_none(value) -> float | None:
    if isinstance(value, bool):
        return None
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # nan / inf ("NaN", "inf" parse too) cannot be shown as an angle
    return number if math.isfinite(number) else None


def photo_fields(p: dict) -> dict:
    """The surface fields of one photo-list entry, as PhotoEntry fields."""
    source = p.get("tiltSource")
    return {"surface": normalize_surface(p.get("surface")),
            "tilt_deg": _float_or_none(p.get("tiltDeg")),
            "tilt_source": source if isinstance(source, str) and source else None}


def timestamps_in(response, key: str) -> list[int]:
    """Timestamps listed under `key` in a register response: plain ints or
    {"timestamp": ...} objects; anything else gives []."""
    if not isinstance(response, dict):
        return []
    raw = response.get(key)
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        ts = item.get("timestamp") if isinstance(item, dict) else item
        if isinstance(ts, int) and not isinstance(ts, bool):
            out.append(ts)
    return out
