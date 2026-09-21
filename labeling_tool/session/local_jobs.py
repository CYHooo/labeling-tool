"""Summaries of already-downloaded jobs (sessions) for the login screen.

A job is ``<data root>/session_<id>/`` with a readable ``manifest.json``.
Listing reads only the manifest and file mtimes, never the images.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from labeling_tool.session.workspace import DEFAULT_DATA_ROOT


@dataclass(frozen=True)
class LocalJob:
    session_id: int
    base: str                      # server the job was fetched from
    inspection_name: str | None
    photo_count: int
    synced_count: int              # photos already uploaded
    modified: float                # latest mtime of manifest / Labeling edits

    @property
    def host(self) -> str:
        return urlparse(self.base).netloc or self.base


def _last_modified(session_dir: Path) -> float:
    """Latest mtime of the manifest and of saved label edits (Labeling/)."""
    times = [(session_dir / "manifest.json").stat().st_mtime]
    labeling = session_dir / "Labeling"
    if labeling.is_dir():
        times += [f.stat().st_mtime for f in labeling.iterdir() if f.is_file()]
    return max(times)


def _read_job(session_dir: Path) -> LocalJob | None:
    suffix = session_dir.name[len("session_"):]
    if not suffix.isdigit():
        return None
    try:
        data = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
        photos = data.get("photos", {})
        return LocalJob(
            session_id=int(suffix),
            base=data.get("base", ""),
            inspection_name=data.get("inspectionName"),
            photo_count=len(photos),
            synced_count=sum(1 for p in photos.values() if p.get("synced")),
            modified=_last_modified(session_dir),
        )
    except (OSError, ValueError, AttributeError):
        return None  # unreadable / half-written manifest: skip, don't break login


def list_local_jobs(root: Path = DEFAULT_DATA_ROOT) -> list[LocalJob]:
    """Downloaded jobs under ``root``, most recently modified first."""
    if not root.is_dir():
        return []
    jobs = [_read_job(d) for d in root.glob("session_*")
            if d.is_dir() and (d / "manifest.json").is_file()]
    return sorted((j for j in jobs if j is not None),
                  key=lambda j: j.modified, reverse=True)
