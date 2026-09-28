"""Split the PyInstaller onedir output into an app layer and a runtime layer.

The app layer is our own code and data; everything else -- Python, PyQt5,
torch, the CUDA runtime -- is the runtime layer, about 1.4 GB that almost
never changes. Publishing them separately lets a code-only release ship
tens of MB instead of 1.5 GB.

The whitelist runs this way round on purpose: anything not named here is
runtime, so a newly added third-party dependency changes the runtime id and
forces a full reinstall, instead of riding along inside a partial app
package that would install missing its own dependency.

Imported by CI (see .github/workflows/build-windows.yml) and by the tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Relative paths (forward slashes) that belong to the app layer. An entry
# ending in "/" matches a whole directory; any other entry matches that one
# file exactly.
APP_LAYER_PREFIXES = (
    "LM_LabelingTool.exe",
    # Written by CI after the runtime id is computed, and it carries the
    # version string -- if it counted as a runtime file the id would move on
    # every release and layering would never engage.
    "build-info.json",
    "_internal/labeling_tool/",
    "_internal/annotation_tool/",
)


def is_app_layer(relpath: str) -> bool:
    """True when this file ships in the small app-only package."""
    rel = relpath.replace("\\", "/")
    for prefix in APP_LAYER_PREFIXES:
        if prefix.endswith("/"):
            if rel.startswith(prefix):
                return True
        elif rel == prefix:
            return True
    return False


def iter_runtime_files(dist_dir: Path):
    """Every runtime-layer file under dist_dir, sorted by relative path."""
    root = Path(dist_dir)
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if not is_app_layer(rel):
            yield rel, path


def compute_runtime_id(dist_dir: Path) -> str:
    """A short, stable identity for the runtime layer's exact contents.

    Hashes each runtime file's relative path and SHA256, in path order, then
    hashes that. Any added, removed, renamed or changed runtime file moves
    the id, so nobody has to remember to bump a version number.
    """
    digest = hashlib.sha256()
    for rel, path in iter_runtime_files(dist_dir):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\0")
    return "r" + digest.hexdigest()[:8]
