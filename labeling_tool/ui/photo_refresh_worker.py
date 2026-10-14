"""Fetch the job's photo list again off the UI thread after an upload that
deleted photos or changed surfaces: the server renumbers the photos, and the
window applies the new numbers when the list arrives."""

from __future__ import annotations

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal

from labeling_tool.api.photos import fetch_all_photos
from labeling_tool.logging_setup import vlog


class PhotoRefreshSignals(QObject):
    # (generation, list[dict] of photos or None on failure): the generation
    # lets a window that started several refreshes apply only the newest one
    finished = pyqtSignal(int, object)


class PhotoRefreshRunnable(QRunnable):
    def __init__(self, client, session_id: int, signals: PhotoRefreshSignals,
                 generation: int = 0):
        super().__init__()
        self._client, self._session_id, self._signals = client, session_id, signals
        self._generation = generation

    def run(self):
        try:
            photos = fetch_all_photos(self._client, self._session_id)
        except Exception as e:  # noqa: BLE001 - never crash the pool thread
            vlog().exception("photo refresh after upload failed: %s", e)
            photos = None
        try:
            self._signals.finished.emit(self._generation, photos)
        except RuntimeError as e:           # the window (and its signals) is gone
            vlog().warning("photo refresh result dropped: %s", e)
