"""Where the app may write files, for source runs and PyInstaller builds.

Source run: every caller keeps its historical location (passed in as
``source_path``), so existing checkouts and their data are untouched.
Frozen on Windows (LabelingTool.exe): writable state lives next to the exe,
so the whole folder is portable and survives replacing ``_internal/`` on
upgrade. This is a published, per-user install base and must never change.
Frozen on Linux: the deb installs to ``/opt``, a root-owned, read-only
directory, so writable state instead lives under the XDG base directories
(``$XDG_DATA_HOME``/``$XDG_CACHE_HOME``, falling back to ``~/.local/share``
and ``~/.cache``).
Read-only bundled resources (ONNX models, BPE vocab) keep using ``__file__``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR_NAME = "lm-labeling-tool"


def is_frozen() -> bool:
    """True inside a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def app_home() -> Path:
    """Folder containing LabelingTool.exe when frozen, else the repo root."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return REPO_ROOT


def bundled_path(*parts: str) -> Path:
    """A read-only resource bundled BESIDE the labeling_tool package.

    The app-layer installer clears _internal/labeling_tool wholesale -- that
    is how stale .pyc from deleted modules get cleaned up -- so anything
    shipping in the RUNTIME layer has to live outside that directory, or the
    app package deletes a file it does not carry and cannot restore.

    Frozen: _MEIPASS is _internal/ in a PyInstaller onedir build, so this
    resolves to _internal/<parts>. From source: the repo layout is
    unchanged, labeling_tool/<parts>.
    """
    if is_frozen():
        return Path(sys._MEIPASS).joinpath(*parts)
    return REPO_ROOT / "labeling_tool" / Path(*parts)


def resource_path(name: str) -> Path:
    """A read-only bundled resource (the app icon, ONNX models).

    Resolved from __file__, so the same path works from source and inside
    PyInstaller's _internal/, where labeling_tool/ is collected whole."""
    return Path(__file__).resolve().parent.parent / "resources" / name


def _xdg_dir(env_var: str, default_suffix: str) -> Path:
    """An XDG base directory, falling back when the variable is unusable.

    The spec requires an absolute path; a blank or relative value -- both seen
    in stripped login environments -- would otherwise resolve against the
    current working directory and scatter user data. Path.home() raises when
    HOME is unset, and this runs during startup, so that falls back too rather
    than leaving the app unable to open a window."""
    raw = (os.environ.get(env_var) or "").strip()
    if raw and Path(raw).is_absolute():
        return Path(raw)
    try:
        home = Path.home()
    except (RuntimeError, OSError):
        home = Path(os.environ.get("TMPDIR") or "/tmp")
    return home / default_suffix


def user_data_home() -> Path:
    """Where the app may write. Beside the executable on Windows (the install
    is per-user and portable); XDG on Linux, where the install lives under
    /opt and is root-owned."""
    if not is_frozen():
        return REPO_ROOT
    if sys.platform == "win32":
        return app_home()
    return _xdg_dir("XDG_DATA_HOME", ".local/share") / APP_DIR_NAME


def user_cache_home() -> Path:
    """Where downloads land: discardable, and kept out of user_data_home() so
    a 1.5 GB update package is not swept into the user's backups.

    Frozen on Windows: the system temp directory (``%TEMP%``), NOT
    app_home() / beside the exe. Unlike user_data_home(), this directory is
    not the published, portable install base -- it is scratch space for an
    in-progress download. installer.iss's [InstallDelete] only clears
    `{app}\\_internal` (full package) or its two app-package subdirectories;
    it does not know about a download directory under `{app}`, and never
    will, so anything placed there survives every future update and even an
    uninstall. The OS already reclaims %TEMP% on its own, which is exactly
    the property an abandoned 1.5 GB download needs.
    Frozen on Linux: XDG_CACHE_HOME (or ~/.cache), same reasoning as
    user_data_home() for XDG_DATA_HOME -- /opt is root-owned and read-only."""
    if not is_frozen():
        return REPO_ROOT / ".cache"
    if sys.platform == "win32":
        return Path(tempfile.gettempdir())
    return _xdg_dir("XDG_CACHE_HOME", ".cache") / APP_DIR_NAME


def writable_path(source_path: Path, frozen_name: str) -> Path:
    """``source_path`` from source; ``user_data_home() / frozen_name`` frozen."""
    return user_data_home() / frozen_name if is_frozen() else Path(source_path)
