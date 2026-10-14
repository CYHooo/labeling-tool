"""Per-session local workspace directory layout.

labeling_tool/data/session_{id}/{Origin,Detected,Labeling,Result,HighLight,Repair15}/ + manifest.json
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from labeling_tool.core.app_paths import writable_path
from labeling_tool.logging_setup import vlog
from labeling_tool.session import mask_store, naming

# Package root (the labeling_tool/ directory); from source, workspace data lives
# under it so a checkout carries its sessions (no ~/ scattering). In the exe it
# lives next to LabelingTool.exe instead.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = writable_path(_PACKAGE_ROOT / "data", "data")


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
    def highlight_dir(self) -> Path:
        return self.session_dir / "HighLight"

    @property
    def repair15_dir(self) -> Path:
        return self.session_dir / "Repair15"

    @property
    def manifest_path(self) -> Path:
        return self.session_dir / "manifest.json"

    def ensure(self) -> None:
        for d in (self.origin_dir, self.detected_dir,
                  self.labeling_dir, self.result_dir,
                  self.highlight_dir, self.repair15_dir):
            d.mkdir(parents=True, exist_ok=True)


    def remove_photo_files(self, filename: str, timestamp: int) -> list[Path]:
        """Delete one photo's files from every job folder.

        Returns the files actually removed; missing files are skipped and a
        file that cannot be deleted is logged without stopping the rest.
        """
        stem = Path(filename).stem
        mask = mask_store.mask_name(filename)
        candidates = [
            self.origin_dir / filename,
            self.detected_dir / naming.detected_mask_filename(timestamp),
            self.labeling_dir / mask,
            self.labeling_dir / mask_store.bbox_name(filename),
            self.highlight_dir / mask,
            self.repair15_dir / mask,
            self.result_dir / f"{stem}.png",
            self.result_dir / f"{stem}.txt",
        ]
        removed: list[Path] = []
        for path in candidates:
            if not path.exists():
                continue
            try:
                path.unlink()
            except OSError as exc:
                vlog().warning("could not remove %s: %s", path, exc)
                continue
            removed.append(path)
        return removed
