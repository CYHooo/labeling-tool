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
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _update_config(**values) -> None:
    """Merge `values` into config.json, keeping every other key."""
    data = load_config()
    data.update(values)
    # On Linux, the default home is an XDG directory that may not exist yet
    # on a fresh install -- app_home() (beside the exe) never needed this
    # because the exe's own directory always exists.
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_config(base: str, api_key: str) -> None:
    _update_config(base=base, apiKey=api_key)


def save_user_id(user_id: str) -> None:
    """The last signed-in ID, filled in next time. Never the password."""
    _update_config(userId=user_id)
