"""Undo / redo for the editable mask layers (crack, spalling).

A step stores, per changed layer, only the bounding rectangle of what
changed -- its pixels before and after -- so a brush stroke on a large
stitched panorama costs kilobytes, not the full frame. The history is
capped by step count and by bytes; the oldest steps go first.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_MAX_STEPS = 20
DEFAULT_MAX_BYTES = 256 * 1024 * 1024


@dataclass
class _Patch:
    layer: str
    y0: int
    x0: int
    before: np.ndarray
    after: np.ndarray

    @property
    def nbytes(self) -> int:
        return self.before.nbytes + self.after.nbytes


def _diff_patch(layer: str, before: np.ndarray | None,
                after: np.ndarray | None) -> _Patch | None:
    """The changed rectangle of one layer, or None when it did not change
    (or cannot be compared: missing or reshaped)."""
    if before is None or after is None or before.shape != after.shape:
        return None
    changed = before != after
    if changed.ndim > 2:
        changed = changed.any(axis=tuple(range(2, changed.ndim)))
    rows = np.flatnonzero(changed.any(axis=1))
    if rows.size == 0:
        return None
    cols = np.flatnonzero(changed.any(axis=0))
    y0, y1, x0, x1 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
    return _Patch(layer, int(y0), int(x0),
                  before[y0:y1, x0:x1].copy(), after[y0:y1, x0:x1].copy())


class MaskHistory:
    def __init__(self, max_steps: int = DEFAULT_MAX_STEPS,
                 max_bytes: int = DEFAULT_MAX_BYTES):
        self.max_steps = max_steps
        self.max_bytes = max_bytes
        self._undo: list[list[_Patch]] = []
        self._redo: list[list[_Patch]] = []

    # -- state
    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def stored_bytes(self) -> int:
        return sum(p.nbytes for step in self._undo + self._redo for p in step)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    # -- recording
    def record(self, before: dict, masks: dict) -> bool:
        """Record the step from `before` to the current `masks` (layer name ->
        array). False when nothing changed. A new step drops the redo list."""
        step = [p for p in (_diff_patch(k, before.get(k), masks.get(k)) for k in masks)
                if p is not None]
        if not step:
            return False
        self._undo.append(step)
        self._redo.clear()
        self._trim()
        return True

    def _trim(self) -> None:
        while len(self._undo) > self.max_steps:
            self._undo.pop(0)
        while len(self._undo) > 1 and self.stored_bytes() > self.max_bytes:
            self._undo.pop(0)

    # -- applying
    def undo(self, masks: dict) -> bool:
        if not self._undo:
            return False
        step = self._undo.pop()
        self._apply(step, masks, "before")
        self._redo.append(step)
        return True

    def redo(self, masks: dict) -> bool:
        if not self._redo:
            return False
        step = self._redo.pop()
        self._apply(step, masks, "after")
        self._undo.append(step)
        return True

    @staticmethod
    def _apply(step: list[_Patch], masks: dict, which: str) -> None:
        for p in step:
            target = masks.get(p.layer)
            if target is None:
                continue
            data = getattr(p, which)
            h, w = data.shape[:2]
            target[p.y0:p.y0 + h, p.x0:p.x0 + w] = data
