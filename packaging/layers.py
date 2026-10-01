"""Split the PyInstaller onedir output into an app layer and a runtime layer.

The app layer is our own code and data; everything else -- Python, PyQt5,
torch, the CUDA runtime -- is the runtime layer, about 1.4 GB that almost
never changes. Publishing them separately lets a code-only release ship
tens of MB instead of 1.5 GB.

The whitelist runs this way round on purpose: anything not named here is
runtime, so a newly added third-party dependency changes the runtime id and
forces a full reinstall, instead of riding along inside a partial app
package that would install missing its own dependency.

Imported by CI (see .github/workflows/release.yml) and by the tests.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

WINDOWS = "win32"
LINUX = "linux"


def current_platform() -> str:
    """The platform whose layout the caller means, defaulting to this host.

    CI builds each platform on its own runner, so the default is right there;
    the tests pass it explicitly to check both rules from one machine."""
    return WINDOWS if sys.platform.startswith("win") else LINUX


def app_entry_name(platform: str | None = None) -> str:
    """The executable PyInstaller emits at the root of the onedir output."""
    return "LM_LabelingTool.exe" if (platform or current_platform()) == WINDOWS \
        else "LM_LabelingTool"


def app_layer_prefixes(platform: str | None = None) -> tuple[str, ...]:
    """Relative paths (forward slashes) that belong to the app layer. An entry
    ending in "/" matches a whole directory; any other entry matches that one
    file exactly.

    The whitelist runs this way round on purpose: anything not named here is
    runtime, so a newly added third-party dependency changes the runtime id
    and forces a full reinstall, instead of riding along inside a partial app
    package that would install missing its own dependency."""
    return (
        app_entry_name(platform),
        # Written by CI after the runtime id is computed, and it carries the
        # version string -- if it counted as a runtime file the id would move
        # on every release and layering would never engage.
        "build-info.json",
        "_internal/labeling_tool/",
        "_internal/annotation_tool/",
    )


# Carved back out of the prefixes above. Nothing needs it today: the ONNX
# models used to sit at _internal/labeling_tool/models/ and were excluded
# here, but they now ship at _internal/models/ instead -- outside the
# directory the app-layer installer clears, which is the only safe place
# for a runtime-layer file (CI run 36670089766).
#
# An entry here MUST NOT start with "_internal/labeling_tool/": that
# directory is wiped before an app-layer install, so anything excluded from
# the app layer while living inside it would be deleted and never restored.
# test_nothing_runtime_layer_lives_under_the_cleared_directory enforces it.
APP_LAYER_EXCLUSIONS: tuple[str, ...] = ()


# Top-level files PyInstaller copies from the BUILD MACHINE's Windows (the
# UCRT forwarders and the VC++ runtime from System32 / the Windows SDK), not
# from any pip package. They ship in the runtime layer as usual but stay out
# of the runtime id: GitHub refreshes its runner image weekly, and image
# 20260925.250.1 moved the id (r7c92a36d) while 20260922.246.2 gave
# ra7115365 for the same commit and the same package versions. They are
# backward compatible, so an install keeping an older copy is fine.
# Only direct children of _internal/: copies inside a package's own
# directory (PyQt5/Qt5/bin/MSVCP140.dll) come from its wheel and do count.
_SYSTEM_RUNTIME_PREFIXES = ("api-ms-win-", "ucrtbase", "vcruntime140",
                            "msvcp140", "concrt140")


def is_build_machine_file(relpath: str, platform: str | None = None) -> bool:
    """True for a system runtime DLL that PyInstaller took from the build
    machine rather than from a dependency.

    Windows-only by construction: the exclusion exists because GitHub refreshes
    its Windows runner image weekly and the UCRT/VC++ forwarders move the
    runtime id for nothing. PyInstaller takes no equivalent files from the
    Linux host -- anything it collects there comes out of a wheel."""
    if (platform or current_platform()) != WINDOWS:
        return False
    rel = relpath.replace("\\", "/")
    if not rel.startswith("_internal/"):
        return False
    name = rel[len("_internal/"):]
    if "/" in name or not name.lower().endswith(".dll"):
        return False
    return name.lower().startswith(_SYSTEM_RUNTIME_PREFIXES)


def is_app_layer(relpath: str, platform: str | None = None) -> bool:
    """True when this file ships in the small app-only package."""
    rel = relpath.replace("\\", "/")
    if any(rel.startswith(x) for x in APP_LAYER_EXCLUSIONS):
        return False
    for prefix in app_layer_prefixes(platform):
        if prefix.endswith("/"):
            if rel.startswith(prefix):
                return True
        elif rel == prefix:
            return True
    return False


def iter_runtime_files(dist_dir: Path, platform: str | None = None):
    """Every runtime-layer file under dist_dir, sorted by relative path."""
    root = Path(dist_dir)
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if not is_app_layer(rel, platform):
            yield rel, path


def runtime_manifest(dist_dir: Path, platform: str | None = None) -> list[tuple[str, int]]:
    """(relative path, size) for every runtime-layer file the id covers,
    sorted by path -- every runtime file except the build machine's own
    system DLLs (see is_build_machine_file).

    This is exactly what compute_runtime_id hashes. CI publishes it so that
    when the id moves unexpectedly, two builds can be diffed file by file
    instead of guessed at.

    Raises FileNotFoundError if dist_dir does not exist."""
    root = Path(dist_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"no such build directory: {root}")
    return [(rel, path.stat().st_size) for rel, path in iter_runtime_files(root, platform)
            if not is_build_machine_file(rel, platform)]


def compute_runtime_id(dist_dir: Path, platform: str | None = None) -> str:
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
    manifest = runtime_manifest(dist_dir, platform)
    if not manifest:
        raise ValueError(f"no runtime-layer files under {dist_dir}")
    digest = hashlib.sha256()
    for rel, size in manifest:
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
    return "r" + digest.hexdigest()[:8]


def stage_app_layer(dist_dir: Path, out_dir: Path, platform: str | None = None) -> tuple[int, int]:
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
        if is_app_layer(rel, platform):
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            app_bytes += size
    return app_bytes, all_bytes


def main(argv: list[str] | None = None) -> int:
    """CLI for CI. PowerShell is the workflow's default shell and has no
    heredoc, so the logic lives here rather than inline in the YAML."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 2 and args[0] == "runtime-id":
        print(compute_runtime_id(Path(args[1])))
        return 0
    if len(args) == 2 and args[0] == "manifest":
        for rel, size in runtime_manifest(Path(args[1])):
            print(f"{size}\t{rel}")
        return 0
    if len(args) == 3 and args[0] == "stage":
        app, whole = stage_app_layer(Path(args[1]), Path(args[2]))
        print(f"app layer: {app / 1024 / 1024:.1f} MB of "
              f"{whole / 1024 / 1024:.1f} MB")
        return 0
    print("usage: layers.py runtime-id <dist>\n"
          "       layers.py manifest <dist>\n"
          "       layers.py stage <dist> <out>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
