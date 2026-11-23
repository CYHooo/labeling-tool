"""A range fetch (범위 지정) is remembered in the job's manifest, so opening
the job again later -- from the local job list or the fetch screen's
"open" -- shows that range again instead of every photo from number 1.

Regression: a job fetched as 278~639 reopened on photo 1 of all 1002, and
the user could not find the photos they had labeled."""

import json

from PyQt5.QtWidgets import QApplication, QMessageBox

from labeling_tool.core import i18n
from labeling_tool.session import naming
from labeling_tool.session.focus import focus_from_manifest
from labeling_tool.session.manifest import Manifest, PhotoEntry

_app = QApplication.instance() or QApplication([])


def _manifest(nums, base="https://x", focus=None):
    mf = Manifest(session_id=95, base=base)
    for n in nums:
        mf.add(PhotoEntry(filename=naming.stitched_filename(1000 + n), timestamp=1000 + n,
                          photo_id=n, report_photo_num=n, px_per_cm=1.0))
    if focus is not None:
        mf.focus_from, mf.focus_to = focus
    return mf


def _names(nums):
    return [naming.stitched_filename(1000 + n) for n in nums]


# ---- manifest + rebuilding the focus ----------------------------------------

def test_manifest_keeps_the_fetched_range(tmp_path):
    path = tmp_path / "manifest.json"
    _manifest([1, 2, 3], focus=(2, 0)).save(path)
    back = Manifest.load(path)
    assert (back.focus_from, back.focus_to) == (2, 0)


def test_a_manifest_written_before_the_range_was_kept_loads_without_one(tmp_path):
    path = tmp_path / "manifest.json"
    _manifest([1, 2]).save(path)
    data = json.loads(path.read_text())
    data.pop("focusRange", None)                       # an older manifest
    path.write_text(json.dumps(data))
    back = Manifest.load(path)
    assert back.focus_from is None and focus_from_manifest(back) is None


def test_focus_from_manifest_lists_the_range_in_photo_order():
    f = focus_from_manifest(_manifest([9, 3, 5, 7, 1], focus=(3, 7)))
    assert (f.from_num, f.to_num) == (3, 7)
    assert list(f.filenames) == _names([3, 5, 7])


def test_focus_to_zero_runs_to_the_last_photo():
    f = focus_from_manifest(_manifest([1, 2, 3, 4], focus=(3, 0)))
    assert list(f.filenames) == _names([3, 4])


def test_no_range_or_an_empty_one_gives_no_focus():
    assert focus_from_manifest(_manifest([1, 2])) is None
    assert focus_from_manifest(_manifest([1, 2], focus=(50, 60))) is None


# ---- jobs fetched before the range was kept: read it from the job log ---------

_LOG = """15:04:17.745 INFO  === session 95 fetch start (base=https://x fromNum=0 toNum=0) ===
15:10:21.006 INFO  download done: 1002 ok, 0 failed
17:38:24.095 INFO  === session 95 fetch start (base=https://x fromNum=278 toNum=639) ===
17:39:52.731 INFO  download done: 362 ok, 0 failed
"""


def test_an_old_job_takes_the_range_of_its_last_fetch_from_the_log(tmp_path):
    from labeling_tool.session.focus import restore_range_from_log
    (tmp_path / "vapi.log").write_text(_LOG, encoding="utf-8")
    mf = _manifest([1, 278, 300, 639, 700])
    assert restore_range_from_log(mf, tmp_path) is True
    assert (mf.focus_from, mf.focus_to) == (278, 639)
    assert list(focus_from_manifest(mf).filenames) == _names([278, 300, 639])


def test_the_log_never_overrides_a_kept_range_or_a_whole_job_fetch(tmp_path):
    from labeling_tool.session.focus import restore_range_from_log
    (tmp_path / "vapi.log").write_text(_LOG, encoding="utf-8")
    kept = _manifest([1, 2], focus=(1, 1))
    assert restore_range_from_log(kept, tmp_path) is False
    assert (kept.focus_from, kept.focus_to) == (1, 1)
    whole = _LOG + "18:00:00.000 INFO  === session 95 fetch start (base=https://x fromNum=0 toNum=0) ===\n"
    (tmp_path / "vapi.log").write_text(whole, encoding="utf-8")
    mf = _manifest([1, 2])
    assert restore_range_from_log(mf, tmp_path) is False and mf.focus_from is None


def test_no_log_or_an_unreadable_one_changes_nothing(tmp_path):
    from labeling_tool.session.focus import restore_range_from_log
    mf = _manifest([1, 2])
    assert restore_range_from_log(mf, tmp_path) is False            # no vapi.log
    (tmp_path / "vapi.log").write_bytes(b"\xff\xfe garbage")
    assert restore_range_from_log(mf, tmp_path) is False


def test_opening_an_old_local_job_restores_and_saves_the_logged_range(monkeypatch, tmp_path):
    from labeling_tool.ui import login_dialog as ld
    monkeypatch.setattr(ld, "load_config", lambda: {"apiKey": "k"})
    monkeypatch.setattr(ld, "save_config", lambda base, key: None)
    monkeypatch.setattr(ld, "DEFAULT_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ld, "attach_session_log", lambda *a: None)
    job = tmp_path / "session_95"
    _manifest([1, 2, 278, 279, 640]).save(job / "manifest.json")     # no focusRange
    (job / "vapi.log").write_text(_LOG, encoding="utf-8")
    dlg = ld.LoginDialog()
    try:
        dlg.tbl_jobs.selectRow(0)
        dlg.btn_open_job.click()
        assert list(dlg.focus.filenames) == _names([278, 279])
        saved = Manifest.load(job / "manifest.json")
        assert (saved.focus_from, saved.focus_to) == (278, 639)
    finally:
        dlg.close()


# ---- fetch screen ------------------------------------------------------------

def _fetch_dialog(monkeypatch, tmp_path, nums=range(1, 11)):
    from labeling_tool.session import workspace as ws_mod
    from labeling_tool.ui import fetch_dialog as fd
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(ws_mod, "DEFAULT_DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(fd, "save_config", lambda *a: None)
    monkeypatch.setattr(fd, "attach_session_log", lambda *a: None)
    photos = [{"timestamp": 1000 + n, "photoId": n, "reportPhotoNum": n, "pxPerCm": 1.0}
              for n in nums]
    monkeypatch.setattr(fd.FetchDialog, "_fetch_all_photos",
                        staticmethod(lambda c, sid: photos))
    monkeypatch.setattr(fd, "download_photos", lambda *a, **k: [])
    i18n.set_language("ko")
    d = fd.FetchDialog(base="https://x", key="k")
    d.client.list_sessions = lambda: [{"sessionId": 95, "inspectionName": "t",
                                       "photoCount": len(photos)}]
    d._load_sessions()
    d.cb_session.setEditText("95")
    return d


def _saved(tmp_path):
    return Manifest.load(tmp_path / "data" / "session_95" / "manifest.json")


def test_a_range_fetch_writes_the_range_into_the_manifest(monkeypatch, tmp_path):
    d = _fetch_dialog(monkeypatch, tmp_path)
    try:
        d.rb_range.setChecked(True)
        d.sp_from.setValue(5)
        d.sp_to.setValue(7)
        d._on_fetch()
        saved = _saved(tmp_path)
        assert (saved.focus_from, saved.focus_to) == (5, 7)
    finally:
        d.close()


def test_fetching_every_photo_forgets_an_old_range(monkeypatch, tmp_path):
    _manifest(range(1, 11), focus=(5, 7)).save(
        tmp_path / "data" / "session_95" / "manifest.json")
    d = _fetch_dialog(monkeypatch, tmp_path)
    monkeypatch.setattr(d, "_ask_existing", lambda sid: "refetch")
    try:
        d._on_fetch()                                  # 사진 전체
        assert _saved(tmp_path).focus_from is None and d.focus is None
    finally:
        d.close()


def test_open_with_a_range_applies_it_and_remembers_it(monkeypatch, tmp_path):
    """The way to set the range on a job fetched before ranges were kept:
    no download, the job opens on 278~639 and stays that way."""
    _manifest(range(1, 11)).save(tmp_path / "data" / "session_95" / "manifest.json")
    d = _fetch_dialog(monkeypatch, tmp_path)
    monkeypatch.setattr(d, "_ask_existing", lambda sid: "open")
    try:
        d.rb_range.setChecked(True)
        d.sp_from.setValue(4)
        d.sp_to.setValue(6)
        d._on_fetch()
        assert list(d.focus.filenames) == _names([4, 5, 6])
        saved = _saved(tmp_path)
        assert (saved.focus_from, saved.focus_to) == (4, 6)
    finally:
        d.close()


def test_open_with_every_photo_keeps_the_remembered_range(monkeypatch, tmp_path):
    _manifest(range(1, 11), focus=(8, 0)).save(
        tmp_path / "data" / "session_95" / "manifest.json")
    d = _fetch_dialog(monkeypatch, tmp_path)
    monkeypatch.setattr(d, "_ask_existing", lambda sid: "open")
    try:
        d._on_fetch()                                  # default 사진 전체 + 열기
        assert list(d.focus.filenames) == _names([8, 9, 10])
    finally:
        d.close()


# ---- local job list ------------------------------------------------------------

def test_opening_a_local_job_restores_its_range(monkeypatch, tmp_path):
    from labeling_tool.ui import login_dialog as ld
    monkeypatch.setattr(ld, "load_config", lambda: {"apiKey": "k"})
    monkeypatch.setattr(ld, "save_config", lambda base, key: None)
    monkeypatch.setattr(ld, "DEFAULT_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ld, "attach_session_log", lambda *a: None)
    _manifest(range(1, 11), focus=(4, 6)).save(tmp_path / "session_95" / "manifest.json")
    dlg = ld.LoginDialog()
    try:
        dlg.tbl_jobs.selectRow(0)
        dlg.btn_open_job.click()
        assert dlg.mode == ld.MODE_SESSION
        assert list(dlg.focus.filenames) == _names([4, 5, 6])
    finally:
        dlg.close()


def test_a_local_job_opens_the_window_with_the_login_focus(monkeypatch):
    from labeling_tool import app as app_module
    from labeling_tool import auth
    from labeling_tool.session.focus import PhotoFocus
    from labeling_tool.ui import login_dialog as ld
    from labeling_tool.update import ui as update_ui
    from labeling_tool.tests.test_app_main import _FakeApp, _FakeSignal
    focus = PhotoFocus(4, 6, ("a.jpg",))
    made = []

    class _Login:
        def __init__(self, *a, user=None, **k):
            self.fewshotRequested = _FakeSignal()
            self.user = auth.User("admin")
            self.mode, self.base, self.key = ld.MODE_SESSION, "", ""
            self.workspace = type("W", (), {"session_id": 95})()
            self.manifest = type("M", (), {"photos": {}})()
            self.focus = focus

        def exec_(self):
            return 1

    class _Window:
        def __init__(self, workspace, manifest, client, focus=None):
            made.append(focus)

        def show(self):
            pass

    monkeypatch.setattr(app_module, "QApplication", _FakeApp)
    monkeypatch.setattr(app_module, "LoginDialog", _Login)
    monkeypatch.setattr(app_module, "ViewerMainWindow", _Window)
    monkeypatch.setattr(_FakeApp, "exec_", lambda self: 0, raising=False)
    monkeypatch.setattr(update_ui, "prompt_pending_update", lambda: None)
    app_module.main([])
    assert made == [focus]
