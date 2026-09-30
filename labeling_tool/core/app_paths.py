"""Where the app may write files, for source runs and PyInstaller builds.

Source run: every caller keeps its historical location (passed in as
``source_path``), so existing checkouts and their data are untouched.
Frozen (LabelingTool.exe): writable state lives next to the exe, so the whole
folder is portable and survives replacing ``_internal/`` on upgrade.
Read-only bundled resources (ONNX models, BPE vocab) keep using ``__file__``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


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


def writable_path(source_path: Path, frozen_name: str) -> Path:
    """``source_path`` from source; ``app_home() / frozen_name`` in the exe."""
    return app_home() / frozen_name if is_frozen() else Path(source_path)
