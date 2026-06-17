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


@dataclass
class Manifest:
    session_id: int
    base: str
    fetched_at: str | None = None
    photos: dict[str, PhotoEntry] = field(default_factory=dict)

    def add(self, entry: PhotoEntry) -> None:
        self.photos[entry.filename] = entry

    def get(self, filename: str) -> PhotoEntry:
        return self.photos[filename]

    def filenames_in_order(self) -> list[str]:
        return [e.filename for e in sorted(
            self.photos.values(), key=lambda e: e.report_photo_num)]

    def mark_synced(self, filenames: list[str], batch_id: str) -> None:
        for fn in filenames:
            e = self.photos.get(fn)
            if e is not None:
                e.synced = True
                e.uploaded_batch_id = batch_id

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": self.session_id,
            "base": self.base,
            "fetchedAt": self.fetched_at,
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
        )
        for fn, d in data.get("photos", {}).items():
            mf.photos[fn] = PhotoEntry(**d)
        return mf
