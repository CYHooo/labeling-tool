"""Which photos a range fetch brought in, so the labeling window can open
on just those (with a switch back to every photo of the job on this PC)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhotoFocus:
    from_num: int          # first photo number of the fetched range
    to_num: int            # last photo number; 0 = to the last photo
    filenames: tuple[str, ...]
