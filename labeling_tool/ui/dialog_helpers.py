"""Shared helpers for the login + fetch dialogs: config persistence
(lifted from the old ConnectDialog)."""

from __future__ import annotations

import json
from pathlib import Path

from labeling_tool.core.app_paths import writable_path

CONFIG_PATH = writable_path(
    Path(__file__).resolve().parent.parent / "config.json", "config.json")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(base: str, api_key: str) -> None:
    # On Linux, the default home is an XDG directory that may not exist yet
    # on a fresh install -- app_home() (beside the exe) never needed this
    # because the exe's own directory always exists.
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps({"base": base, "apiKey": api_key}, indent=2),
        encoding="utf-8")
