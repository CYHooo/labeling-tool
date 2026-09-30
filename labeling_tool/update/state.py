"""Remember when we last checked for updates and which version was skipped.

last_check is a record, not a throttle: every launch checks. A 24-hour
throttle used to sit here, and it hid a release published a few hours after
the day's first launch until the next day -- users ended up pressing the
manual check button instead."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from labeling_tool.core.app_paths import user_data_home

STATE_NAME = "update-state.json"


@dataclass(frozen=True)
class UpdateState:
    last_check: str | None = None
    skipped_version: str | None = None


def _path(home: Path | None) -> Path:
    return (Path(home) if home is not None else user_data_home()) / STATE_NAME


def load(home: Path | None = None) -> UpdateState:
    try:
        data = json.loads(_path(home).read_text(encoding="utf-8"))
        return UpdateState(data.get("last_check"), data.get("skipped_version"))
    except (OSError, ValueError, AttributeError):
        return UpdateState()


def save(st: UpdateState, home: Path | None = None) -> None:
    try:
        _path(home).write_text(json.dumps(
            {"last_check": st.last_check, "skipped_version": st.skipped_version},
            indent=2), encoding="utf-8")
    except OSError:
        pass  # a read-only install must not break the app over bookkeeping


def mark_checked(home: Path | None = None, now: datetime | None = None) -> None:
    st = load(home)
    save(UpdateState((now or datetime.now(timezone.utc)).isoformat(),
                     st.skipped_version), home)


def skip_version(version: str, home: Path | None = None) -> None:
    st = load(home)
    save(UpdateState(st.last_check, version), home)
