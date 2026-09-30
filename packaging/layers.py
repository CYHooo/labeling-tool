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


# Carved back out of the prefixes above. The MobileSAM ONNX models live
# inside labeling_tool/ but are fixed pretrained weights -- 42.4 MB that
# never changes, which was over half of every app-layer update. Swapping a
# model is a full reinstall, same as swapping torch.
APP_LAYER_EXCLUSIONS = (
    "_internal/labeling_tool/models/",
)


def is_app_layer(relpath: str) -> bool:
    """True when this file ships in the small app-only package."""
    rel = relpath.replace("\\", "/")
    if any(rel.startswith(x) for x in APP_LAYER_EXCLUSIONS):
        return False
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
    """A short identity for the runtime layer, measured from the build.

    Hashes each runtime file's relative path and SIZE -- never its contents.
    Two PyInstaller runs of the same commit emit different bytes (timestamps
    go into the files; CI runs 36421966949 and 36424404832 produced
    ra9adeaed and r138b837f), so hashing contents would move the id on every
    release and the app package would never match anything. Paths and sizes
    survive that.

    Measuring the build directly also means nobody has to judge which config
    affects the runtime layer: adding a dependency, upgrading torch or
    excluding a CUDA library all change the listing, while editing an icon
    path in the spec does not.

    The trade-off is on record in
    test_runtime_id_does_not_see_content_changes_at_equal_size: a dependency
    whose contents change without any file changing name or size will not
    move the id.

    Raises FileNotFoundError if dist_dir does not exist, and ValueError if it
    holds no runtime-layer files at all -- both mean the caller pointed at
    the wrong directory, and a hash of nothing would look authoritative.
    """
    root = Path(dist_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"no such build directory: {root}")
    digest = hashlib.sha256()
    count = 0
    for rel, path in iter_runtime_files(root):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        count += 1
    if count == 0:
        raise ValueError(f"no runtime-layer files under {root}")
    return "r" + digest.hexdigest()[:8]


def stage_app_layer(dist_dir: Path, out_dir: Path) -> tuple[int, int]:
    """Copy just the app layer into out_dir. Returns (app bytes, all bytes).

    A separate directory is what the app-layer installer compiles from, so
    the layer rule above is the single place that decides what ships in a
    partial update."""
    import shutil

    src, dst = Path(dist_dir), Path(out_dir)
    app_bytes = all_bytes = 0
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        size = path.stat().st_size
        all_bytes += size
        rel = path.relative_to(src).as_posix()
        if is_app_layer(rel):
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            app_bytes += size
    return app_bytes, all_bytes


def main(argv: list[str] | None = None) -> int:
    """CLI for CI. PowerShell is the workflow's default shell and has no
    heredoc, so the logic lives here rather than inline in the YAML."""
    import sys

    args = sys.argv[1:] if argv is None else argv
    if len(args) == 2 and args[0] == "runtime-id":
        print(compute_runtime_id(Path(args[1])))
        return 0
    if len(args) == 3 and args[0] == "stage":
        app, whole = stage_app_layer(Path(args[1]), Path(args[2]))
        print(f"app layer: {app / 1024 / 1024:.1f} MB of "
              f"{whole / 1024 / 1024:.1f} MB")
        return 0
    print("usage: layers.py runtime-id <dist>\n"
          "       layers.py stage <dist> <out>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
