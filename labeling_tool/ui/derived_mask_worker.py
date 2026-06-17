"""Background generation of the derived (highlight + repair15) masks.

Runs generate_derived_masks off the UI thread via QThreadPool so saving a
large image never freezes the GUI. Emits done(token, highlight, repair15)
back to the UI thread, where the controller refreshes the canvas only if the
token still matches the on-screen image.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal

from labeling_tool.core.derived_masks import generate_derived_masks
from labeling_tool.logging_setup import vlog


class DerivedMaskSignals(QObject):
    done = pyqtSignal(str, object, object)   # token, highlight, repair15|None


class DerivedMaskRunnable(QRunnable):
    def __init__(self, *, crack, spalling, px_per_cm,
                 highlight_path, repair15_path, token, signals):
        super().__init__()
        self._crack = crack
        self._spalling = spalling
        self._px_per_cm = px_per_cm
        self._highlight_path = highlight_path
        self._repair15_path = repair15_path
        self._token = token
        self._signals = signals

    def run(self):
        try:
            hi, r15 = generate_derived_masks(
                self._crack, self._spalling, self._px_per_cm,
                self._highlight_path, self._repair15_path)
            self._signals.done.emit(self._token, hi, r15)
        except Exception as e:  # noqa: BLE001 - never crash the pool thread
            vlog().exception("derived mask worker failed: %s", e)
