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


def writable_path(source_path: Path, frozen_name: str) -> Path:
    """``source_path`` from source; ``app_home() / frozen_name`` in the exe."""
    return app_home() / frozen_name if is_frozen() else Path(source_path)
