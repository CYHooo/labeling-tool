"""Fetching a job that is already on this PC: open it, or fetch again
without losing the upload records or photos outside the new range."""
import pytest
from PyQt5.QtWidgets import QApplication

from labeling_tool.session import workspace as ws_mod
from labeling_tool.session.manifest import Manifest, PhotoEntry
from labeling_tool.ui import fetch_dialog as fd

_app = QApplication.instance() or QApplication([])


def _entry(name, num, synced=False, batch=None, px=1.0):
    return PhotoEntry(filename=name, timestamp=num, photo_id=num, report_photo_num=num,
                      px_per_cm=px, synced=synced, uploaded_batch_id=batch)


def test_keep_from_carries_upload_records_and_photos_outside_the_new_range():
    old = Manifest(session_id=7, base="https://a")
    old.add(_entry("1.jpg", 1, synced=True, batch="b1"))
    old.add(_entry("2.jpg", 2, synced=True, batch="b1"))
    new = Manifest(session_id=7, base="https://a")
    new.add(_entry("2.jpg", 2, px=9.0))          # re-fetched: fresh server values
    new.add(_entry("3.jpg", 3))                  # newly fetched
    new.keep_from(old)
    assert new.filenames_in_order() == ["1.jpg", "2.jpg", "3.jpg"]
    assert new.get("1.jpg").synced and new.get("1.jpg").uploaded_batch_id == "b1"
    assert new.get("2.jpg").synced and new.get("2.jpg").uploaded_batch_id == "b1"
    assert new.get("2.jpg").px_per_cm == 9.0
    assert not new.get("3.jpg").synced


@pytest.fixture
def dlg(monkeypatch, tmp_path):
    monkeypatch.setattr(ws_mod, "DEFAULT_DATA_ROOT", tmp_path)
    monkeypatch.setattr(fd, "save_config", lambda *a: None)
    monkeypatch.setattr(fd, "attach_session_log", lambda *a: None)
    d = fd.FetchDialog(base="https://a", key="k")
    d._selected_sid = lambda: 7
    d.sp_from.setValue(0)
    d.sp_to.setValue(0)
    yield d
    d.close()


def _existing(tmp_path):
    ws = ws_mod.Workspace(root=tmp_path, session_id=7)
    ws.ensure()
    m = Manifest(session_id=7, base="https://a", inspection_name="점검")
    m.add(_entry("1.jpg", 1, synced=True, batch="b1"))
    m.save(ws.manifest_path)
    return ws


def _server(monkeypatch, photos):
    calls = []
    monkeypatch.setattr(fd.FetchDialog, "_fetch_all_photos", staticmethod(lambda c, sid: (calls.append(sid), photos)[1]))
    monkeypatch.setattr(fd, "download_photos", lambda *a, **k: [])
    return calls


def _photo(num):
    return {"timestamp": num, "photoId": num, "reportPhotoNum": num, "pxPerCm": 2.0,
            "stitchedUrl": "u", "maskUrl": "m"}


def test_opening_an_existing_job_skips_the_server(dlg, tmp_path, monkeypatch):
    _existing(tmp_path)
    calls = _server(monkeypatch, [_photo(1)])
    dlg._ask_existing = lambda sid: "open"
    dlg._on_fetch()
    assert calls == []
    assert dlg.result() == dlg.Accepted
    assert dlg.manifest.get("1.jpg").synced
    assert dlg.workspace.session_dir == tmp_path / "session_7"


def test_fetching_again_keeps_the_upload_records(dlg, tmp_path, monkeypatch):
    ws = _existing(tmp_path)
    _server(monkeypatch, [_photo(2)])
    dlg._ask_existing = lambda sid: "refetch"
    dlg._on_fetch()
    assert dlg.result() == dlg.Accepted
    saved = Manifest.load(ws.manifest_path)
    assert set(saved.photos) == {"1.jpg", fd.naming.stitched_filename(2)}
    assert saved.inspection_name == "점검"
    assert saved.get("1.jpg").synced


def test_cancelling_leaves_everything_as_it_was(dlg, tmp_path, monkeypatch):
    ws = _existing(tmp_path)
    before = ws.manifest_path.read_text(encoding="utf-8")
    calls = _server(monkeypatch, [_photo(2)])
    dlg._ask_existing = lambda sid: None
    dlg._on_fetch()
    assert calls == []
    assert dlg.result() != dlg.Accepted
    assert ws.manifest_path.read_text(encoding="utf-8") == before


def test_a_new_job_is_fetched_without_asking(dlg, tmp_path, monkeypatch):
    _server(monkeypatch, [_photo(1)])
    asked = []
    dlg._ask_existing = lambda sid: asked.append(sid)
    dlg._on_fetch()
    assert asked == []
    assert dlg.result() == dlg.Accepted


def _existing_from(tmp_path, base):
    ws = ws_mod.Workspace(root=tmp_path, session_id=7)
    ws.ensure()
    m = Manifest(session_id=7, base=base)
    m.add(_entry("1.jpg", 1, synced=True, batch="b1"))
    m.save(ws.manifest_path)
    return ws


@pytest.mark.parametrize("choice", ["open", "refetch"])
def test_a_same_numbered_job_from_another_server_is_refused(dlg, tmp_path, monkeypatch, choice):
    """session_7 on disk came from server A; the user picked server B's job 7
    -- a different job in the same folder. Opening or refetching it would
    send A's labels to B, so it is refused before anything happens."""
    ws = _existing_from(tmp_path, "https://other-server")
    before = ws.manifest_path.read_text(encoding="utf-8")
    calls = _server(monkeypatch, [_photo(1)])
    asked, warned = [], []
    dlg._ask_existing = lambda sid: (asked.append(sid), choice)[1]
    monkeypatch.setattr(fd.QMessageBox, "warning", lambda *a, **k: warned.append(a))
    dlg._on_fetch()
    assert warned and asked == [] and calls == []
    assert dlg.result() != dlg.Accepted
    assert ws.manifest_path.read_text(encoding="utf-8") == before


def test_a_job_without_a_recorded_server_still_asks(dlg, tmp_path, monkeypatch):
    _existing_from(tmp_path, "")
    _server(monkeypatch, [_photo(1)])
    asked = []
    dlg._ask_existing = lambda sid: (asked.append(sid), "open")[1]
    dlg._on_fetch()
    assert asked == [7] and dlg.result() == dlg.Accepted


def test_a_trailing_slash_is_the_same_server(dlg, tmp_path, monkeypatch):
    _existing_from(tmp_path, "https://a/")
    _server(monkeypatch, [_photo(1)])
    dlg._ask_existing = lambda sid: "open"
    dlg._on_fetch()
    assert dlg.result() == dlg.Accepted


def test_fetching_a_photo_again_keeps_its_upload_record(dlg, tmp_path, monkeypatch):
    ws = ws_mod.Workspace(root=tmp_path, session_id=7)
    ws.ensure()
    m = Manifest(session_id=7, base="https://a")
    name = fd.naming.stitched_filename(1)
    m.add(_entry(name, 1, synced=True, batch="b1"))
    m.save(ws.manifest_path)
    _server(monkeypatch, [_photo(1)])
    dlg._ask_existing = lambda sid: "refetch"
    dlg._on_fetch()
    saved = Manifest.load(ws.manifest_path)
    assert saved.get(name).synced and saved.get(name).uploaded_batch_id == "b1"
    assert saved.get(name).px_per_cm == 2.0      # fresh server value
