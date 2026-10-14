"""After an upload: the job's photo list is fetched again in the background
and the local photo numbers and surface fields follow the server."""
from PyQt5.QtWidgets import QApplication

from labeling_tool.session import photo_edits as E
from labeling_tool.session.manifest import Manifest, PhotoEntry

_app = QApplication.instance() or QApplication([])


def _manifest(*nums):
    m = Manifest(session_id=45, base="")
    for n in nums:
        m.add(PhotoEntry(filename=f"stitched_{n}.jpg", timestamp=n, photo_id=n,
                         report_photo_num=n, px_per_cm=2.0))
    return m


# ---------------------------------------------------------------- apply_photo_refresh
def test_new_photo_numbers_are_written():
    m = _manifest(1, 3)
    changed = E.apply_photo_refresh(m, [{"timestamp": 1, "reportPhotoNum": 1},
                                        {"timestamp": 3, "reportPhotoNum": 2}])
    assert changed is True
    assert m.get("stitched_3.jpg").report_photo_num == 2
    assert m.get("stitched_1.jpg").report_photo_num == 1


def test_nothing_new_reports_no_change():
    m = _manifest(1, 2)
    assert E.apply_photo_refresh(m, [{"timestamp": 1, "reportPhotoNum": 1},
                                     {"timestamp": 2, "reportPhotoNum": 2}]) is False


def test_a_photo_the_server_did_not_list_is_kept():
    m = _manifest(1, 2)
    E.apply_photo_refresh(m, [{"timestamp": 1, "reportPhotoNum": 1}])
    assert m.get("stitched_2.jpg").report_photo_num == 2
    assert len(m.photos) == 2


def test_a_photo_only_the_server_has_is_not_added():
    m = _manifest(1)
    E.apply_photo_refresh(m, [{"timestamp": 9, "reportPhotoNum": 1}])
    assert list(m.photos) == ["stitched_1.jpg"]


def test_server_surface_fields_are_updated_and_the_local_edit_kept():
    m = _manifest(1)
    e = m.get("stitched_1.jpg")
    e.surface, e.surface_edit, e.delete_pending = "wall", "floor", True
    changed = E.apply_photo_refresh(m, [{"timestamp": 1, "reportPhotoNum": 1,
                                         "surface": "ceiling", "tiltDeg": 12.5,
                                         "tiltSource": "manual"}])
    assert changed is True
    assert (e.surface, e.tilt_deg, e.tilt_source) == ("ceiling", 12.5, "manual")
    assert e.surface_edit == "floor" and e.delete_pending is True


def test_missing_surface_fields_count_as_null():
    m = _manifest(1)
    e = m.get("stitched_1.jpg")
    e.surface, e.tilt_deg, e.tilt_source = "wall", 3.0, "auto"
    assert E.apply_photo_refresh(m, [{"timestamp": 1, "reportPhotoNum": 1}]) is True
    assert (e.surface, e.tilt_deg, e.tilt_source) == (None, None, None)


def test_a_malformed_entry_is_skipped():
    m = _manifest(1)
    assert E.apply_photo_refresh(m, [{"reportPhotoNum": 4}, "x",
                                     {"timestamp": "1", "reportPhotoNum": 5}]) is False
    assert m.get("stitched_1.jpg").report_photo_num == 1


# ---------------------------------------------------------------- fetch_all_photos
class _PagedClient:
    def __init__(self, photos, page=100):
        self.photos, self.calls = photos, []

    def list_photos(self, session_id, *, offset=0, limit=100, **_kw):
        self.calls.append((session_id, offset, limit))
        return {"photos": self.photos[offset:offset + limit], "total": len(self.photos)}


def test_fetch_all_photos_follows_the_pages():
    from labeling_tool.api.photos import fetch_all_photos
    photos = [{"timestamp": n} for n in range(250)]
    client = _PagedClient(photos)
    assert fetch_all_photos(client, 45) == photos
    assert client.calls == [(45, 0, 100), (45, 100, 100), (45, 200, 100)]


def test_the_fetch_dialog_uses_the_shared_fetch():
    from labeling_tool.ui.fetch_dialog import FetchDialog
    client = _PagedClient([{"timestamp": 1}])
    assert FetchDialog._fetch_all_photos(client, 7) == [{"timestamp": 1}]


# ---------------------------------------------------------------- the worker
def _run(client):
    from labeling_tool.ui.photo_refresh_worker import (
        PhotoRefreshRunnable, PhotoRefreshSignals)
    signals = PhotoRefreshSignals()
    got = []
    signals.done.connect(got.append)
    PhotoRefreshRunnable(client, 45, signals).run()
    QApplication.processEvents()
    return got


def test_the_worker_hands_over_every_photo():
    photos = [{"timestamp": n} for n in range(3)]
    assert _run(_PagedClient(photos)) == [photos]


def test_the_worker_reports_a_failure_as_none():
    class Broken:
        def list_photos(self, *a, **k):
            raise ConnectionError("offline")
    assert _run(Broken()) == [None]
