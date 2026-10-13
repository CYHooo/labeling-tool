"""Damage classes of the label mask.

Pixel value = class id: 1 crack (a line), 2 spalling (an area), and classes
users add through the server (API v1.0.16 V5 / V6), ids 3..254, always areas.
The server owns the numbering so every PC means the same thing by a value;
this module keeps a per-server cache so the tool works offline.
"""

from __future__ import annotations

import colorsys
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

from labeling_tool.core.app_paths import user_data_home

CRACK_ID = 1
SPALLING_ID = 2
MAX_CLASS_ID = 254          # 255 stays free: it marks legacy 0/255 binary masks
UNKNOWN_RGB = (150, 150, 150)
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Distinct from crack red, spalling green and the unknown grey.
PALETTE = ("#3C8CFF", "#FFAA00", "#B05CFF", "#00C8C8", "#FF5CC8",
           "#8C6E3C", "#C8C83C", "#5C5CFF", "#FF7F50", "#2E8B57")


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    s = color.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


@dataclass(frozen=True)
class LabelClass:
    class_id: int
    name: str
    kind: str                 # "line" | "area"
    color: str                # "#RRGGBB"
    builtin: bool = False

    @property
    def rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.color)


BUILTIN_CLASSES = (
    LabelClass(CRACK_ID, "crack", "line", "#FF3C3C", True),
    LabelClass(SPALLING_ID, "spalling", "area", "#3CE63C", True),
)
_BUILTIN_I18N = {CRACK_ID: "cat_crack", SPALLING_ID: "cat_spalling"}


class ClassRegistry:
    """The built-in classes plus the server's user classes, by id."""

    def __init__(self, extra: Iterable[LabelClass] = ()):
        by_id = {c.class_id: c for c in BUILTIN_CLASSES}
        for c in extra:
            if c.class_id in (CRACK_ID, SPALLING_ID):
                continue                       # built-ins are fixed
            if 3 <= c.class_id <= MAX_CLASS_ID:
                by_id[c.class_id] = c
        self._by_id = dict(sorted(by_id.items()))

    def classes(self) -> list[LabelClass]:
        return list(self._by_id.values())

    def user_classes(self) -> list[LabelClass]:
        return [c for c in self._by_id.values() if not c.builtin]

    def ids(self) -> list[int]:
        return list(self._by_id)

    def get(self, cid: int) -> LabelClass | None:
        return self._by_id.get(int(cid))

    def __contains__(self, cid) -> bool:
        return int(cid) in self._by_id

    def rgb(self, cid: int) -> tuple[int, int, int]:
        c = self.get(cid)
        return c.rgb if c is not None else UNKNOWN_RGB

    def is_area(self, cid: int) -> bool:
        """Unknown ids (added elsewhere, not synced yet) count as areas."""
        c = self.get(cid)
        return c is None or c.kind == "area"

    def display_name(self, cid: int, tr: Callable[..., str]) -> str:
        if int(cid) in _BUILTIN_I18N:
            return tr(_BUILTIN_I18N[int(cid)])
        c = self.get(cid)
        return c.name if c is not None else tr("class_unknown", id=int(cid))

    def with_class(self, c: LabelClass) -> "ClassRegistry":
        return ClassRegistry([*self.user_classes(), c])

    def to_payload(self) -> dict:
        """Same shape as the V5 response (built-ins included)."""
        return {"classes": [
            {"classId": c.class_id, "name": c.name, "kind": c.kind,
             "color": c.color, "builtin": c.builtin}
            for c in self.classes()]}


def parse_class(d: dict) -> LabelClass:
    """One V5 / V6 class entry; ValueError when it cannot be used."""
    cid = d.get("classId")
    if not isinstance(cid, int) or isinstance(cid, bool):
        raise ValueError(f"bad classId: {cid!r}")
    name = str(d.get("name") or "").strip()
    if not name:
        raise ValueError(f"class {cid} has no name")
    kind = d.get("kind") if d.get("kind") in ("line", "area") else "area"
    color = d.get("color") or ""
    if not _HEX.match(color):
        color = PALETTE[cid % len(PALETTE)]
    return LabelClass(cid, name, kind, color.upper(), bool(d.get("builtin")))


def parse_classes(payload: dict) -> ClassRegistry:
    """A V5 response (or our cache, same shape); bad entries are skipped."""
    if not isinstance(payload, dict):
        return ClassRegistry()
    entries = payload.get("classes")
    if not isinstance(entries, list):
        return ClassRegistry()
    out = []
    for d in entries:
        try:
            out.append(parse_class(d))
        except (ValueError, TypeError, AttributeError):
            from labeling_tool.logging_setup import vlog
            vlog().warning("skipping class entry %r", d)
    return ClassRegistry(out)


def cache_dir() -> Path:
    return user_data_home() / "label-classes"


def cache_file(base_url: str, root: Path | None = None) -> Path:
    parsed = urlparse(base_url.strip())
    host = parsed.netloc or parsed.path or "default"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", host.rstrip("/"))
    return Path(root or cache_dir()) / f"{safe}.json"


def load_cached(base_url: str, root: Path | None = None) -> ClassRegistry:
    try:
        text = cache_file(base_url, root).read_text(encoding="utf-8")
        return parse_classes(json.loads(text))
    except (OSError, ValueError):
        return ClassRegistry()


def save_cached(base_url: str, registry: ClassRegistry,
                root: Path | None = None) -> None:
    path = cache_file(base_url, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(registry.to_payload(), f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def pick_color(registry: ClassRegistry) -> str:
    """The first palette colour not in use; then evenly spread hues."""
    used = {c.color.upper() for c in registry.classes()}
    for color in PALETTE:
        if color.upper() not in used:
            return color
    n = len(used)
    while True:
        h = (n * 0.618033988749895) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.65, 0.95)
        color = "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))
        if color not in used and color not in PALETTE:
            return color
        n += 1
