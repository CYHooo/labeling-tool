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


# The PyInstaller spec decides WHICH packages enter the runtime layer
# (collect_all, excludes, binaries, datas), so a change here can move the
# runtime layer without any dependency version changing.
RUNTIME_SPEC_FILES = ("packaging/labeling_tool.spec",)


def compute_runtime_id(repo_root: Path, freeze_text: str) -> str:
    """A short identity for the runtime layer: what is installed, plus what
    gets packed.

    NOT the built files. Two PyInstaller runs of the same commit emit
    different bytes (CI runs 36421966949 and 36424404832 produced ra9adeaed
    and r138b837f), so hashing the output would move the id on every release
    and the app package would never match anything.

    `freeze_text` is `pip freeze` from the build environment, taken after
    every dependency is installed. Hashing the resolved versions rather than
    the requirement files is what makes this sound: requirements.txt pins
    nothing (`PyQt5>=5.15`), so pip can resolve a different version with no
    file changing. That matters because the layer split cuts through those
    packages -- PyQt5's Python code rides inside the exe (app layer) while
    its .pyd files are runtime layer, so shipping an app package across a
    version change installs half an upgrade that cannot import.

    Raises ValueError on an empty freeze and FileNotFoundError on a missing
    spec, rather than quietly hashing less than it should.
    """
    root = Path(repo_root)
    # pip freeze's order is not guaranteed stable between runs
    pins = sorted(line.strip() for line in freeze_text.splitlines()
                  if line.strip() and not line.lstrip().startswith("#"))
    if not pins:
        raise ValueError("empty pip freeze: the build environment was not captured")
    digest = hashlib.sha256()
    digest.update("\n".join(pins).encode("utf-8"))
    digest.update(b"\0")
    for rel in RUNTIME_SPEC_FILES:
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / rel).read_bytes())
        digest.update(b"\0")
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
    if len(args) == 3 and args[0] == "runtime-id":
        freeze = Path(args[2]).read_text(encoding="utf-8")
        print(compute_runtime_id(Path(args[1]), freeze))
        return 0
    if len(args) == 3 and args[0] == "stage":
        app, whole = stage_app_layer(Path(args[1]), Path(args[2]))
        print(f"app layer: {app / 1024 / 1024:.1f} MB of "
              f"{whole / 1024 / 1024:.1f} MB")
        return 0
    print("usage: layers.py runtime-id <repo-root> <pip-freeze-file>\n"
          "       layers.py stage <dist> <out>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
