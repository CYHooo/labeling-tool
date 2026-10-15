"""Local session manifest: bridges GUI filenames and Viewer API timestamps.

Persists per-photo metadata fetched from the server plus upload (sync) state, so
labeling can resume offline and uploads stay idempotent across runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class PhotoEntry:
    filename: str
    timestamp: int
    photo_id: int
    report_photo_num: int
    px_per_cm: float
    scale_source: str = "aruco"
    synced: bool = False
    uploaded_batch_id: str | None = None
    # surface the server reports for the photo (floor / wall / ceiling)
    surface: str | None = None
    tilt_deg: float | None = None
    tilt_source: str | None = None
    # local edits not yet uploaded: a changed surface, a delete mark
    surface_edit: str | None = None
    delete_pending: bool = False
    # the server no longer has the photo (someone else deleted it): it is
    # left out of uploads, its local files stay (an AI re-run may bring it
    # back); cleared when the server lists it again
    server_missing: bool = False


@dataclass
class Manifest:
    session_id: int
    base: str
    fetched_at: str | None = None
    photos: dict[str, PhotoEntry] = field(default_factory=dict)
    # server-side inspection name, shown in the local job list; None for
    # manifests written before it was recorded
    inspection_name: str | None = None

    def add(self, entry: PhotoEntry) -> None:
        self.photos[entry.filename] = entry

    def remove(self, filename: str) -> None:
        self.photos.pop(filename, None)

    def get(self, filename: str) -> PhotoEntry:
        return self.photos[filename]

    def filenames_in_order(self) -> list[str]:
        return [e.filename for e in sorted(
            self.photos.values(), key=lambda e: e.report_photo_num)]

    def keep_from(self, previous: "Manifest") -> None:
        """Fold in the manifest this fetch replaces: photos outside the new
        range stay listed (their label edits are still on disk), and photos
        fetched again keep their upload record. A photo fetched again is
        on the server, so its server_missing stays False."""
        for name, old in previous.photos.items():
            entry = self.photos.get(name)
            if entry is None:
                self.add(old)
            else:
                entry.synced = old.synced
                entry.uploaded_batch_id = old.uploaded_batch_id
                entry.surface_edit = old.surface_edit
                entry.delete_pending = old.delete_pending
        if not self.inspection_name:
            self.inspection_name = previous.inspection_name

    def mark_synced(self, filenames: list[str], batch_id: str) -> None:
        for fn in filenames:
            e = self.photos.get(fn)
            if e is not None:
                e.synced = True
                e.uploaded_batch_id = batch_id

    def mark_server_missing(self, timestamps) -> list[str]:
        """Flag the photos with these timestamps as gone from the server.
        Returns the filenames newly flagged."""
        wanted = {int(t) for t in timestamps}
        changed = []
        for fn, e in self.photos.items():
            if int(e.timestamp) in wanted and not e.server_missing:
                e.server_missing = True
                changed.append(fn)
        return changed

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": self.session_id,
            "base": self.base,
            "fetchedAt": self.fetched_at,
            "inspectionName": self.inspection_name,
            "photos": {fn: asdict(e) for fn, e in self.photos.items()},
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        mf = cls(
            session_id=data["sessionId"],
            base=data.get("base", ""),
            fetched_at=data.get("fetchedAt"),
            inspection_name=data.get("inspectionName"),
        )
        for fn, d in data.get("photos", {}).items():
            mf.photos[fn] = PhotoEntry(**d)
        return mf
