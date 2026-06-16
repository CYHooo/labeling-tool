"""Download V1 photo pairs (stitched + mask) into the local workspace.

Sequential with per-photo error capture: one bad URL never aborts the
batch. Returns the list of failed entries for the UI to surface/retry.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import requests

from labeling_tool.session import naming
from labeling_tool.logging_setup import vlog

ProgressFn = Callable[[int, int], None]


def _download_to(url: str, dest: Path, timeout: int = 60) -> int:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return len(resp.content)


def download_photos(photos: list[dict], origin_dir: Path, detected_dir: Path,
                    progress: ProgressFn | None = None,
                    timeout: int = 60) -> list[dict]:
    total = len(photos)
    vlog().info("download start: %d photos", total)
    failures: list[dict] = []
    for i, p in enumerate(photos, start=1):
        ts = int(p["timestamp"])
        stitched_dest = origin_dir / naming.stitched_filename(ts)
        mask_dest = detected_dir / naming.detected_mask_filename(ts)
        t = time.perf_counter()
        try:
            sb = _download_to(p["stitchedUrl"], stitched_dest, timeout)
            mb = _download_to(p["maskUrl"], mask_dest, timeout)
            vlog().info("download ts=%s stitched=%dB mask=%dB (%.0f ms) [%d/%d]",
                        ts, sb, mb, (time.perf_counter() - t) * 1000, i, total)
        except Exception as e:  # noqa: BLE001 - capture & continue by design
            # Remove any partial pair so the GUI never sees an orphan.
            stitched_dest.unlink(missing_ok=True)
            mask_dest.unlink(missing_ok=True)
            vlog().error("download FAILED ts=%s: %s", ts, e)
            failures.append({"timestamp": ts, "error": str(e)})
        if progress is not None:
            progress(i, total)
    vlog().info("download done: %d ok, %d failed",
                total - len(failures), len(failures))
    return failures
