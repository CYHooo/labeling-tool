"""Per-session local workspace directory layout.

labeling_tool/data/session_{id}/{Origin,Detected,Labeling,Result}/ + manifest.json
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Package root (the labeling_tool/ directory); workspace data lives under it
# so a checkout of the tool carries its sessions with it (no ~/ scattering).
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = _PACKAGE_ROOT / "data"


@dataclass
class Workspace:
    root: Path
    session_id: int

    @classmethod
    def default(cls, session_id: int) -> "Workspace":
        return cls(root=DEFAULT_DATA_ROOT, session_id=session_id)

    @property
    def session_dir(self) -> Path:
        return self.root / f"session_{self.session_id}"

    @property
    def origin_dir(self) -> Path:
        return self.session_dir / "Origin"

    @property
    def detected_dir(self) -> Path:
        return self.session_dir / "Detected"

    @property
    def labeling_dir(self) -> Path:
        return self.session_dir / "Labeling"

    @property
    def result_dir(self) -> Path:
        return self.session_dir / "Result"

    @property
    def rebuilt_dir(self) -> Path:
        return self.session_dir / "Rebuilt"

    @property
    def manifest_path(self) -> Path:
        return self.session_dir / "manifest.json"

    def ensure(self) -> None:
        for d in (self.origin_dir, self.detected_dir,
                  self.labeling_dir, self.result_dir, self.rebuilt_dir):
            d.mkdir(parents=True, exist_ok=True)


def list_local_session_ids(root: Path = DEFAULT_DATA_ROOT) -> list[int]:
    """Session ids already downloaded under ``root`` (have a manifest.json).

    Used by the offline open dropdown. Returns ascending int ids; a missing
    root yields an empty list.
    """
    if not root.exists():
        return []
    ids: list[int] = []
    for d in root.glob("session_*"):
        if not d.is_dir() or not (d / "manifest.json").exists():
            continue
        suffix = d.name[len("session_"):]
        if suffix.isdigit():
            ids.append(int(suffix))
    return sorted(ids)
