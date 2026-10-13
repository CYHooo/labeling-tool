"""Ask the server for the class list off the UI thread (it may be slow or
unreachable); the window applies the result when it arrives."""

from __future__ import annotations

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal

from labeling_tool.api.class_sync import sync_classes
from labeling_tool.logging_setup import vlog


class ClassSyncSignals(QObject):
    done = pyqtSignal(object, str)          # ClassRegistry, status


class ClassSyncRunnable(QRunnable):
    def __init__(self, client, base_url: str, signals: ClassSyncSignals):
        super().__init__()
        self._client, self._base, self._signals = client, base_url, signals

    def run(self):
        try:
            registry, status = sync_classes(self._client, self._base)
            self._signals.done.emit(registry, status)
        except Exception as e:  # noqa: BLE001 - never crash the pool thread
            vlog().exception("class sync worker failed: %s", e)
