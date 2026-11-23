"""Which photos a range fetch brought in, so the labeling window can open
on just those (with a switch back to every photo of the job on this PC)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PhotoFocus:
    from_num: int          # first photo number of the fetched range
    to_num: int            # last photo number; 0 = to the last photo
    filenames: tuple[str, ...]


def focus_for_range(manifest, from_num: int, to_num: int) -> PhotoFocus | None:
    """The manifest's photos numbered from_num..to_num (to 0 = to the last),
    in photo-number order; None when no photo falls in the range."""
    names = tuple(
        e.filename for e in sorted(manifest.photos.values(),
                                   key=lambda e: e.report_photo_num)
        if e.report_photo_num >= from_num
        and (not to_num or e.report_photo_num <= to_num))
    return PhotoFocus(from_num, to_num, names) if names else None


# Written by the fetch screen BEFORE it downloads (fetch_dialog._on_fetch),
# and by the downloader once it finished (api/downloader.py).
_FETCH_START = re.compile(
    r"=== session \d+ fetch start \(base=\S* fromNum=(\d+) toNum=(\d+)\) ===")
_DOWNLOAD_DONE = "download done:"


def _last_completed_fetch(text: str) -> tuple[int, int] | None:
    """(fromNum, toNum) of the last fetch whose download finished. A fetch
    that failed or matched no photos logged its start but never replaced
    the manifest, so it does not count."""
    pending = done = None
    for line in text.splitlines():
        m = _FETCH_START.search(line)
        if m:
            pending = (int(m.group(1)), int(m.group(2)))
        elif _DOWNLOAD_DONE in line and pending is not None:
            done, pending = pending, None
    return done


def restore_range_from_log(manifest, session_dir) -> bool:
    """Give a manifest written before ranges were kept the range of its last
    completed fetch, read from the job's vapi.log. Never for a manifest this
    version wrote (its focusRange, even null, is authoritative), and a
    whole-job fetch leaves the job whole. Returns True when the range was set
    (the caller saves the manifest, which records it for good)."""
    if getattr(manifest, "focus_recorded", True) or \
            getattr(manifest, "focus_from", None) is not None:
        return False
    try:
        text = (Path(session_dir) / "vapi.log").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    last = _last_completed_fetch(text)
    if last is None or last == (0, 0):
        return False
    manifest.focus_from, manifest.focus_to = last
    manifest.focus_recorded = True
    return True


def focus_from_manifest(manifest) -> PhotoFocus | None:
    """The range the job was last fetched with, or None for a whole job."""
    if getattr(manifest, "focus_from", None) is None:
        return None
    return focus_for_range(manifest, manifest.focus_from, manifest.focus_to or 0)
