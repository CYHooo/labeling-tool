"""Shared helpers for the login + fetch dialogs: config persistence and the
Rebuilt/ prebuild progress loop (lifted from the old ConnectDialog)."""

from __future__ import annotations

import json
from pathlib import Path

from labeling_tool.rebuild_cache import prebuild_rebuilt

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(base: str, api_key: str) -> None:
    CONFIG_PATH.write_text(
        json.dumps({"base": base, "apiKey": api_key}, indent=2),
        encoding="utf-8")


def run_prebuild(ws, timestamps, progress, status_label) -> None:
    """Pre-compute the Rebuilt/ cache for every photo with a visible progress
    bar, so the labeling window opens instantly instead of freezing while it
    rebuilds the first image on the UI thread."""
    if not timestamps:
        return
    from PyQt5.QtWidgets import QApplication
    progress.setVisible(True)
    progress.setRange(0, len(timestamps))
    progress.setValue(0)

    def _prog(done, total):
        progress.setValue(done)
        status_label.setText(f"재구성(rebuild) {done}/{total}")
        QApplication.processEvents()

    prebuild_rebuilt(ws.origin_dir, ws.detected_dir, ws.rebuilt_dir,
                     timestamps, progress=_prog)
