"""Build identity written next to the exe by CI (build-info.json).

Source runs have no such file: they report DEV_VERSION and no variant, which
is what makes the updater a no-op outside a real release build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from labeling_tool.core.app_paths import app_home

BUILD_INFO_NAME = "build-info.json"
DEV_VERSION = "0.0.0-dev"
VARIANTS = ("lite", "full")


@dataclass(frozen=True)
class BuildInfo:
    version: str
    variant: str | None
    commit: str | None

    @property
    def is_release_build(self) -> bool:
        # Must be a valid numeric version (e.g., 1.0.0, 1.2.3) and have a known variant.
        # Rejects both the literal DEV_VERSION and dev builds like "dev-abc1234".
        if self.variant not in VARIANTS:
            return False
        parts = str(self.version).lstrip("vV").split(".")
        return all(p.isdigit() for p in parts)


def read_build_info(home: Path | None = None) -> BuildInfo:
    """Read build-info.json; anything missing or malformed reads as a dev build."""
    base = Path(home) if home is not None else app_home()
    try:
        # utf-8-sig: a BOM in a hand-edited or Windows-tool-written
        # build-info.json must not silently make this look malformed and
        # disable updates.
        data = json.loads((base / BUILD_INFO_NAME).read_text(encoding="utf-8-sig"))
        version = str(data["version"])
        variant = data.get("variant")
    except (OSError, ValueError, KeyError, TypeError):
        return BuildInfo(DEV_VERSION, None, None)
    return BuildInfo(version,
                     variant if variant in VARIANTS else None,
                     str(data["commit"]) if data.get("commit") else None)
