# annotation_tool/core/class_registry.py
"""Runtime class definitions (pixel value -> name/color + export priority).

The registry is the single source of truth for classes while the tool runs.
It is seeded from the factory defaults in `configs` and persisted to a global
JSON file (`configs.CLASSES_FILE`) so user-added classes, renames, color and
priority changes survive restarts and are shared by all datasets.

JSON layout:
    {"classes": [{"id": 1, "name": "joint", "color": [255, 0, 0]}, ...],
     "export_order": [2, 1, ...]}   # low -> high priority
"""
from __future__ import annotations

import json
from pathlib import Path

from annotation_tool import configs

# 0 is the background value in exported uint8 masks
MIN_CLASS_ID = 1
MAX_CLASS_ID = 255


def _to_rgb(color) -> tuple[int, int, int]:
    rgb = tuple(int(v) for v in color)
    if len(rgb) != 3 or any(v < 0 or v > 255 for v in rgb):
        raise ValueError(f"invalid RGB color: {color!r}")
    return rgb


class ClassRegistry:
    def __init__(self, names: dict[int, str], colors: dict[int, tuple],
                 export_order: list[int]):
        ids = set(names)
        if set(colors) != ids or set(export_order) != ids or len(export_order) != len(ids):
            raise ValueError("names, colors and export_order must cover the same class ids")
        for cid in ids:
            if not MIN_CLASS_ID <= cid <= MAX_CLASS_ID:
                raise ValueError(f"class id {cid} out of range [{MIN_CLASS_ID}, {MAX_CLASS_ID}]")
        self._names = {int(c): str(n) for c, n in names.items()}
        self._colors = {int(c): _to_rgb(v) for c, v in colors.items()}
        self._order = [int(c) for c in export_order]

    # --- construction / persistence ---
    @classmethod
    def from_configs(cls) -> "ClassRegistry":
        """Factory defaults from configs.py (only classes listed in CLASS_IDS)."""
        ids = list(configs.CLASS_IDS)
        return cls(
            names={c: configs.CLASSES[c] for c in ids},
            colors={c: configs.CLASS_COLORS[c] for c in ids},
            export_order=[c for c in configs.EXPORT_ORDER if c in ids],
        )

    @classmethod
    def load(cls, path: str | Path, fallback: "ClassRegistry") -> "ClassRegistry":
        """Load from JSON; a missing file yields a copy of `fallback`.

        A malformed file raises ValueError so the caller can tell the user
        instead of silently overwriting their class definitions."""
        path = Path(path)
        if not path.exists():
            return fallback.copy()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data["classes"]
            names = {int(e["id"]): str(e["name"]) for e in entries}
            colors = {int(e["id"]): e["color"] for e in entries}
            order = [int(c) for c in data["export_order"]]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"malformed classes file {path}: {exc}") from exc
        if len(names) != len(entries):
            raise ValueError(f"duplicate class ids in {path}")
        return cls(names, colors, order)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "classes": [{"id": c, "name": self._names[c], "color": list(self._colors[c])}
                        for c in self.class_ids],
            "export_order": list(self._order),
        }
        # write to a temp file first so a crash never leaves a half-written file
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def copy(self) -> "ClassRegistry":
        return ClassRegistry(dict(self._names), dict(self._colors), list(self._order))

    # --- queries ---
    @property
    def class_ids(self) -> list[int]:
        return sorted(self._names)

    @property
    def export_order(self) -> list[int]:
        """Class ids from low to high priority (later overwrites earlier)."""
        return list(self._order)

    def name(self, cid: int) -> str:
        return self._names[cid]

    def color(self, cid: int) -> tuple[int, int, int]:
        return self._colors[cid]

    def colors(self) -> dict[int, tuple[int, int, int]]:
        return dict(self._colors)

    # --- edits ---
    def _check_name(self, name: str, exclude: int | None = None) -> str:
        name = name.strip()
        if not name:
            raise ValueError("class name must not be empty")
        if any(n == name for c, n in self._names.items() if c != exclude):
            raise ValueError(f"class name already exists: {name}")
        return name

    def add(self, name: str, color) -> int:
        """Add a class with the smallest free pixel value; it gets top priority."""
        name = self._check_name(name)
        rgb = _to_rgb(color)
        free = next((c for c in range(MIN_CLASS_ID, MAX_CLASS_ID + 1)
                     if c not in self._names), None)
        if free is None:
            raise ValueError("no free pixel value left (1-255 all used)")
        self._names[free] = name
        self._colors[free] = rgb
        self._order.append(free)
        return free

    def rename(self, cid: int, name: str) -> None:
        if cid not in self._names:
            raise KeyError(cid)
        self._names[cid] = self._check_name(name, exclude=cid)

    def set_color(self, cid: int, color) -> None:
        if cid not in self._names:
            raise KeyError(cid)
        self._colors[cid] = _to_rgb(color)

    def move_priority(self, cid: int, delta: int) -> None:
        """Move `cid` within export_order; +1 = higher priority. Clamped at the ends."""
        i = self._order.index(cid)
        j = max(0, min(i + delta, len(self._order) - 1))
        self._order.insert(j, self._order.pop(i))
