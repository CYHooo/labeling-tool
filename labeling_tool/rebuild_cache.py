"""Pre-compute the intensity-guided rebuild for downloaded photos.

The labeling window runs `process_one` the first time each image is viewed,
synchronously on the UI thread — on a fresh session that froze the window on
the first panorama. Running it up front (during the connection wizard's
progress phase) populates the `Rebuilt/` cache so the labeling window opens
instantly.

Two speedups vs. the naive version:
  * `compute_length=False` — the rebuild's gap-bridged centerline/length is
    discarded here, so skip it (~a third of the per-image cost).
  * a process pool — `process_one` is CPU-bound, so images are rebuilt in
    parallel across cores instead of one-by-one.

The output MUST be byte-identical to what `MainWindow._show_image` would write
on demand: a 3-channel BGR PNG with the rebuilt crack in the R channel, stored
under `Rebuilt/<detected_mask_name>` (i.e. `stitched_{ts}_mask.png`).
"""

from __future__ import annotations

import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import cv2

from labeling_tool.session import naming
from labeling_tool.session import mask_store

ProgressFn = Callable[[int, int], None]

# Cap workers: each holds a full panorama + rebuild intermediates in RAM, so
# more processes mostly cost memory once a few cores are busy.
MAX_WORKERS = 4


def _prebuild_one(origin_path: str, detected_path: str, out_path: str) -> str | None:
    """Build one Rebuilt mask. Returns an error string, or None on success.

    Top-level + path-only args so it is picklable for the process pool.
    """
    try:
        origin_bgr = cv2.imread(origin_path)
        raw = cv2.imread(detected_path, cv2.IMREAD_UNCHANGED)
        if origin_bgr is None or raw is None:
            return "missing origin or detected mask"
        rgb = mask_store.build_rebuilt_rgb(origin_bgr, raw)
        cv2.imwrite(out_path, rgb)
        return None
    except Exception as e:  # noqa: BLE001 - reported back to the caller
        return str(e)


def prebuild_rebuilt(origin_dir, detected_dir, rebuilt_dir,
                     timestamps: list[int],
                     progress: ProgressFn | None = None,
                     workers: int | None = None) -> list[dict]:
    """Populate rebuilt_dir for each timestamp; skip already-cached entries.

    Runs in a process pool (CPU-bound). Returns per-photo failures
    `[{"timestamp", "error"}]`; one bad photo never aborts the batch.
    A cache entry is reused only when it is fresh (exists and not older than
    its Detected source); a re-downloaded (newer) Detected mask regenerates it.
    """
    origin_dir = Path(origin_dir)
    detected_dir = Path(detected_dir)
    rebuilt_dir = Path(rebuilt_dir)
    rebuilt_dir.mkdir(parents=True, exist_ok=True)

    total = len(timestamps)
    jobs = []   # (ts, origin_path, detected_path, out_path)
    for ts in timestamps:
        out_path = rebuilt_dir / naming.detected_mask_filename(ts)
        det_path = detected_dir / naming.detected_mask_filename(ts)
        if out_path.exists() and (not det_path.exists()
                                  or out_path.stat().st_mtime >= det_path.stat().st_mtime):
            continue   # fresh cache, skip
        jobs.append((
            ts,
            str(origin_dir / naming.stitched_filename(ts)),
            str(detected_dir / naming.detected_mask_filename(ts)),
            str(out_path),
        ))

    done = total - len(jobs)            # already-cached count toward progress
    if progress is not None:
        progress(done, total)
    failures: list[dict] = []
    if not jobs:
        return failures

    if workers is None:
        workers = max(1, min(os.cpu_count() or 1, MAX_WORKERS))
    workers = min(workers, len(jobs))

    if workers <= 1:
        for ts, op, dp, outp in jobs:
            err = _prebuild_one(op, dp, outp)
            if err:
                failures.append({"timestamp": ts, "error": err})
            done += 1
            if progress is not None:
                progress(done, total)
        return failures

    # 'spawn' gives each worker a clean interpreter (no inherited Qt/fork state).
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
        fut_to_ts = {ex.submit(_prebuild_one, op, dp, outp): ts
                     for ts, op, dp, outp in jobs}
        for fut in as_completed(fut_to_ts):
            ts = fut_to_ts[fut]
            try:
                err = fut.result()
            except Exception as e:  # noqa: BLE001
                err = str(e)
            if err:
                failures.append({"timestamp": ts, "error": err})
            done += 1
            if progress is not None:
                progress(done, total)
    return failures
