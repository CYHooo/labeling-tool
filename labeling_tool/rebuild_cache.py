"""Pre-compute the intensity-guided rebuild for downloaded photos.

The labeling window runs `process_one` (skeletonize + intensity-guided width
fit + centerline) the first time each image is viewed, synchronously on the UI
thread — on a freshly downloaded session that freezes the window on the first
photo. Running it up front (during the connection wizard's progress phase)
populates the `Rebuilt/` cache so the labeling window opens instantly.

The output MUST be byte-identical to what `MainWindow._show_image` would write
on demand, or the core's `find_mask_path` won't treat it as a cache hit:
a 3-channel BGR PNG with the rebuilt crack in the R channel, stored under
`Rebuilt/<detected_mask_name>` (i.e. `stitched_{ts}_mask.png`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from labeling_tool.core.rebuild import process_one
from labeling_tool.session import naming

ProgressFn = Callable[[int, int], None]


def prebuild_rebuilt(origin_dir, detected_dir, rebuilt_dir,
                     timestamps: list[int],
                     progress: ProgressFn | None = None) -> list[dict]:
    """Populate rebuilt_dir for each timestamp; skip already-cached entries.

    Returns a list of per-photo failures `[{"timestamp", "error"}]`; one bad
    photo never aborts the batch. Idempotent: an existing cache file is left
    untouched, so the call is resumable across runs.
    """
    origin_dir = Path(origin_dir)
    detected_dir = Path(detected_dir)
    rebuilt_dir = Path(rebuilt_dir)
    rebuilt_dir.mkdir(parents=True, exist_ok=True)

    total = len(timestamps)
    failures: list[dict] = []
    for i, ts in enumerate(timestamps, start=1):
        out_path = rebuilt_dir / naming.detected_mask_filename(ts)
        try:
            if not out_path.exists():
                origin_path = origin_dir / naming.stitched_filename(ts)
                detected_path = detected_dir / naming.detected_mask_filename(ts)
                origin_bgr = cv2.imread(str(origin_path))
                raw = cv2.imread(str(detected_path), cv2.IMREAD_UNCHANGED)
                if origin_bgr is None or raw is None:
                    raise RuntimeError(
                        f"missing origin or detected mask for ts={ts}")
                # Mirror _show_image: crack lives in the R channel (BGR idx 2),
                # or the whole image if the mask is single-channel.
                coarse_gray = raw[..., 2] if raw.ndim == 3 else raw
                guided, _, _ = process_one(origin_bgr, coarse_gray)
                rgb = np.zeros((*guided.shape, 3), dtype=np.uint8)
                rgb[..., 2] = guided
                cv2.imwrite(str(out_path), rgb)
        except Exception as e:  # noqa: BLE001 - capture & continue by design
            failures.append({"timestamp": ts, "error": str(e)})
        if progress is not None:
            progress(i, total)
    return failures
