"""Filename <-> timestamp <-> S3 key conversions for the Viewer API.

Convention (api-reference_v1.0.8): stitched_{timestampMs}.jpg paired with
mask_{timestampMs}.png, high_{timestampMs}.png, 15_{timestampMs}.png.
S3 keys: results/{sessionId}/masks/{mask|high|15}_{ts}.png.
"""

from __future__ import annotations

import re

_TS_RE = re.compile(r"^(?:stitched|mask)_(\d+)\.(?:jpg|jpeg|png)$", re.IGNORECASE)


def stitched_filename(timestamp: int) -> str:
    return f"stitched_{int(timestamp)}.jpg"


def mask_filename(timestamp: int) -> str:
    return f"mask_{int(timestamp)}.png"


def detected_mask_filename(timestamp: int) -> str:
    """Local AI-mask filename that the core find_mask_path pairs to
    stitched_{ts}.jpg (via the '_mask' suffix). Distinct from the S3 upload
    name mask_{ts}.png used by the upload steps."""
    return f"stitched_{int(timestamp)}_mask.png"


def timestamp_from_filename(filename: str) -> int:
    m = _TS_RE.match(filename)
    if not m:
        raise ValueError(f"not a stitched/mask filename: {filename!r}")
    return int(m.group(1))


def mask_s3_key(session_id: int, timestamp: int) -> str:
    return f"results/{int(session_id)}/masks/mask_{int(timestamp)}.png"


def high_filename(timestamp: int) -> str:
    return f"high_{int(timestamp)}.png"


def repair15_filename(timestamp: int) -> str:
    return f"15_{int(timestamp)}.png"


def high_s3_key(session_id: int, timestamp: int) -> str:
    return f"results/{int(session_id)}/masks/high_{int(timestamp)}.png"


def repair15_s3_key(session_id: int, timestamp: int) -> str:
    return f"results/{int(session_id)}/masks/15_{int(timestamp)}.png"
