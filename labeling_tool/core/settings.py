"""UI preferences stored next to the exe (ui-settings.json).

Kept apart from config.json: that file holds credentials and is rewritten
wholesale by save_config(base, key), which would drop anything else in it.
Every failure here is swallowed — a read-only install must not break the app
over a preference.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from labeling_tool.core.app_paths import app_home

SETTINGS_NAME = "ui-settings.json"
DEFAULT_LANGUAGE = "ko"


def _path(home: Path | None) -> Path:
    return (Path(home) if home is not None else app_home()) / SETTINGS_NAME


def load_settings(home: Path | None = None) -> dict:
    try:
        data = json.loads(_path(home).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict, home: Path | None = None) -> None:
    """Write ui-settings.json atomically.

    Writes to a sibling temp file first, then os.replace()s it into place,
    so a crash mid-write (or a second instance writing concurrently) can
    never leave a truncated/partial ui-settings.json behind -- a plain
    write_text() truncates the existing file before writing the new
    content, so a crash between those two steps loses the file entirely.
    """
    path = _path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2, ensure_ascii=False))
            os.replace(tmp_name, path)
        except OSError:
            try:
                os.remove(tmp_name)
            except OSError:
                pass
            raise
    except OSError:
        pass


def get_language(home: Path | None = None) -> str:
    from labeling_tool.core.i18n import LANGUAGES
    lang = load_settings(home).get("lang")
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


def set_language_setting(code: str, home: Path | None = None) -> None:
    data = load_settings(home)
    data["lang"] = code
    save_settings(data, home)
