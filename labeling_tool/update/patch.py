"""Apply an app-layer update zip to an installed copy, with a journal.

The zip carries the app layer -- our own code, a few MB -- plus
manifest.json (version, runtime id, platform, every file's SHA-256). The
swap moves each replaced file into .update-backup/ before moving the new
one in, journalling every move first, so a failure rolls back exactly and a
crash mid-swap is undone by recover() on the next start.

Windows: a running .exe cannot be overwritten but can be renamed, so moving
it into the backup works while the app runs. Linux: /opt is root-owned, so
the app runs this module as root via `pkexec <exe> --apply-update`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from labeling_tool.update import checker
from labeling_tool.update.version import read_build_info

MANIFEST_NAME = "manifest.json"
STAGING, BACKUP, JOURNAL = ".update-staging", ".update-backup", ".update-journal"


def APP_LAYER_PREFIXES(platform: str | None = None) -> tuple[str, ...]:
    """Must equal packaging/layers.app_layer_prefixes (test_update_zip.py)."""
    exe = "LM_LabelingTool.exe" if (platform or checker.current_platform()) == checker.WINDOWS \
        else "LM_LabelingTool"
    return (exe, "build-info.json", "_internal/labeling_tool/", "_internal/annotation_tool/")


class PatchError(Exception):
    """The zip cannot be applied; nothing on disk was changed (or it was rolled back)."""


@dataclass(frozen=True)
class PatchManifest:
    version: str
    runtime: str
    platform: str
    files: dict[str, str]


def _is_app_layer(rel: str, platform: str) -> bool:
    for prefix in APP_LAYER_PREFIXES(platform):
        if (prefix.endswith("/") and rel.startswith(prefix)) or rel == prefix:
            return True
    return False


def _safe_rel(rel: str, platform: str) -> str:
    p = PurePosixPath(rel)
    # A backslash or drive colon is a separator or root on Windows, where
    # "a/..\\..\\x" would walk out of the install dir past the POSIX check.
    if "\\" in rel or ":" in rel or p.is_absolute() or ".." in p.parts \
            or rel != p.as_posix():
        raise PatchError(f"unsafe path in update: {rel!r}")
    if not _is_app_layer(rel, platform):
        raise PatchError(f"not an app-layer file: {rel!r}")
    return rel


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)


def read_manifest(zip_path: Path) -> PatchManifest:
    try:
        with zipfile.ZipFile(zip_path) as z:
            data = json.loads(z.read(MANIFEST_NAME).decode("utf-8"))
        return PatchManifest(str(data["version"]), str(data["runtime"]),
                             str(data["platform"]), dict(data["files"]))
    except (KeyError, ValueError, zipfile.BadZipFile, OSError) as exc:
        raise PatchError(f"not an update zip: {exc}") from exc


def _installed_app_files(root: Path, platform: str) -> list[str]:
    out = []
    for path in root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if not rel.startswith((STAGING, BACKUP)) and _is_app_layer(rel, platform):
                out.append(rel)
    return out


def _rollback(root: Path, journal: list[list[str]]) -> None:
    journal_path = root / JOURNAL
    while journal:
        op, a, b = journal[-1]
        src, dst = Path(b), Path(a)   # undo: move it back where it came from
        if src.exists():
            _move(src, dst)
        # Shrink the journal as we go so an interrupted rollback can be re-run
        # without undoing the same entry twice (which would clobber a restored file).
        journal.pop()
        if journal:
            journal_path.write_text(json.dumps(journal), encoding="utf-8")
    shutil.rmtree(root / STAGING, ignore_errors=True)
    (root / JOURNAL).unlink(missing_ok=True)


def _stage(zip_path: Path, root: Path, staging: Path, expected_sha256: str,
           platform: str) -> PatchManifest:
    """Verify the zip and unpack it into staging; touches nothing else."""
    if _sha256(zip_path) != expected_sha256.lower():
        raise PatchError("update zip does not match its published checksum")
    m = read_manifest(zip_path)
    installed = read_build_info(root)
    if m.platform != platform:
        raise PatchError(f"update is for {m.platform}, this install is {platform}")
    if not installed.runtime or m.runtime != installed.runtime:
        raise PatchError(f"update needs runtime {m.runtime}, installed is {installed.runtime}")
    for rel in m.files:
        _safe_rel(rel, platform)
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist()) - {MANIFEST_NAME}
        if names != set(m.files):
            raise PatchError("zip contents do not match its manifest")
        for rel in m.files:
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(rel))
            if _sha256(target) != m.files[rel]:
                raise PatchError(f"{rel} does not match the manifest")
            # write_bytes drops the mode; keep the executable bit the zip
            # carries, else the file being replaced has.
            mode = (z.getinfo(rel).external_attr >> 16) & 0o777
            if not mode and (root / rel).exists():
                mode = (root / rel).stat().st_mode & 0o777
            if mode:
                target.chmod(mode)
    return m


def apply_patch(zip_path: Path, install_dir: Path, expected_sha256: str,
                platform: str | None = None) -> PatchManifest:
    platform = platform or checker.current_platform()
    root = Path(install_dir)
    # A swap that never finished holds the only copy of the old files in the
    # backup; undo it before anything below deletes the backup. On Linux this
    # is the recovery path, since only the root-run apply can touch /opt.
    if (root / JOURNAL).exists():
        recover(root)
    staging = root / STAGING
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        # Work on a private copy: the original may sit in a user-writable cache
        # while this runs as root, so hash and read only what we copied.
        local_zip = staging / "update.zip"
        shutil.copyfile(Path(zip_path), local_zip)
        m = _stage(local_zip, root, staging, expected_sha256, platform)
        local_zip.unlink()
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    backup = root / BACKUP
    shutil.rmtree(backup, ignore_errors=True)
    journal: list[list[str]] = []
    journal_path = root / JOURNAL

    def record(op: str, src: Path, dst: Path) -> None:
        journal.append([op, str(src), str(dst)])
        journal_path.write_text(json.dumps(journal), encoding="utf-8")

    try:
        stale = set(_installed_app_files(root, platform)) - set(m.files)
        for rel in sorted(set(m.files) | stale):
            current = root / rel
            if current.exists():
                record("backup", current, backup / rel)
                _move(current, backup / rel)
            if rel in m.files:
                record("install", staging / rel, current)
                _move(staging / rel, current)
    except Exception as exc:  # noqa: BLE001 - any failure must roll back
        _rollback(root, journal)
        raise PatchError(f"could not apply the update: {exc}") from exc
    journal_path.unlink(missing_ok=True)
    shutil.rmtree(staging, ignore_errors=True)
    return m


def recover(install_dir: Path) -> bool:
    """Undo a swap that never finished. Call first thing at startup."""
    root = Path(install_dir)
    journal_path = root / JOURNAL
    if not journal_path.exists():
        return False
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        journal = []
    _rollback(root, journal)
    return True


def cleanup(install_dir: Path) -> None:
    """Drop the previous version's files once the new one is running."""
    root = Path(install_dir)
    if (root / JOURNAL).exists():
        return
    shutil.rmtree(root / BACKUP, ignore_errors=True)
    shutil.rmtree(root / STAGING, ignore_errors=True)
