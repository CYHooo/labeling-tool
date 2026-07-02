# annotation_tool/ui/worker.py
"""Background inference worker. Runs Segmenter.predict off the UI thread."""
from __future__ import annotations

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition


class InferenceWorker(QThread):
    result = pyqtSignal(np.ndarray)
    error = pyqtSignal(str)

    def __init__(self, segmenter, parent=None):
        super().__init__(parent)
        self._seg = segmenter
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._pending = None      # latest request only
        self._running = True

    def request(self, points_xy, labels, box):
        self._mutex.lock()
        if self._running:
            self._pending = (list(points_xy), list(labels), box)
            self._cond.wakeOne()
        self._mutex.unlock()

    def stop(self):
        self._mutex.lock()
        self._running = False
        self._cond.wakeOne()
        self._mutex.unlock()
        if not self.wait(5000):  # predict() may be mid-inference; give it time
            self.terminate()     # last resort if still stuck
            self.wait()

    def run(self):
        while True:
            self._mutex.lock()
            while self._running and self._pending is None:
                self._cond.wait(self._mutex)
            if not self._running:
                self._mutex.unlock()
                return
            req = self._pending
            self._pending = None
            self._mutex.unlock()

            points, labels, box = req
            try:
                mask = self._seg.predict(points, labels, box)
                self.result.emit(np.ascontiguousarray(mask))
            except Exception as e:  # surface to UI, keep thread alive
                self.error.emit(f"{type(e).__name__}: {e}")
