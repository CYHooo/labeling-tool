# annotation_tool/core/mask_state.py
"""Independent binary class layers with priority flattening + undo/redo.

Layer keys are pixel-class values (e.g. 1=joint, 2=concrete, 3=scalebar).
Classes may be added at runtime via `ensure_layer`. Export flattens to a single
uint8 array using an export order (low -> high priority) so that
higher-priority classes overwrite lower-priority ones on overlapping pixels.
"""
from __future__ import annotations

from collections import deque

import numpy as np

from annotation_tool.configs import CLASS_IDS, EXPORT_ORDER, UNDO_DEPTH


class MaskState:
    def __init__(self, height: int, width: int, class_ids=None):
        self.h = height
        self.w = width
        ids = CLASS_IDS if class_ids is None else class_ids
        self.layers = {c: np.zeros((height, width), dtype=bool) for c in ids}
        self._undo_stack: deque[dict] = deque(maxlen=UNDO_DEPTH)
        self._redo_stack: deque[dict] = deque()

    # --- internal snapshot helpers ---
    def _snapshot(self) -> dict:
        return {c: m.copy() for c, m in self.layers.items()}

    def _push_undo(self) -> None:
        self._undo_stack.append(self._snapshot())
        self._redo_stack.clear()

    def _restore(self, snapshot: dict) -> None:
        # a snapshot taken before ensure_layer() lacks the newer layers; keep
        # them (empty) so the class stays usable after undo
        for c in self.layers:
            snapshot.setdefault(c, np.zeros((self.h, self.w), dtype=bool))
        self.layers = snapshot

    def _check_class(self, class_id: int) -> None:
        if class_id not in self.layers:
            raise ValueError(f"unknown class_id {class_id}; valid: {sorted(self.layers)}")

    def ensure_layer(self, class_id: int) -> None:
        """Create an empty layer for a class added at runtime (no undo entry)."""
        if class_id not in self.layers:
            self.layers[class_id] = np.zeros((self.h, self.w), dtype=bool)

    # --- editing ops ---
    def add(self, class_id: int, mask: np.ndarray) -> None:
        self._check_class(class_id)
        self._push_undo()
        self.layers[class_id] |= mask.astype(bool)

    def erase(self, class_id: int, mask: np.ndarray) -> None:
        self._check_class(class_id)
        self._push_undo()
        self.layers[class_id] &= ~mask.astype(bool)

    def clear(self, class_id: int) -> None:
        self._check_class(class_id)
        self._push_undo()
        self.layers[class_id][:] = False

    # --- undo / redo ---
    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo(self) -> None:
        if not self.can_undo:
            return
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())

    def redo(self) -> None:
        if not self.can_redo:
            return
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())

    # --- io / export ---
    def flatten(self, export_order=None) -> np.ndarray:
        order = EXPORT_ORDER if export_order is None else export_order
        out = np.zeros((self.h, self.w), dtype=np.uint8)
        for c in order:
            if c in self.layers:
                out[self.layers[c]] = c
        return out

    def load_from(self, mask_uint8: np.ndarray) -> None:
        assert mask_uint8.dtype == np.uint8, f"expected uint8, got {mask_uint8.dtype}"
        assert mask_uint8.shape == (self.h, self.w), f"shape mismatch: {mask_uint8.shape} vs {(self.h, self.w)}"
        self._push_undo()
        for c in self.layers:
            self.layers[c] = (mask_uint8 == c)

    def stats(self) -> dict[int, float]:
        total = self.h * self.w
        return {c: float(m.sum()) / total for c, m in self.layers.items()}
