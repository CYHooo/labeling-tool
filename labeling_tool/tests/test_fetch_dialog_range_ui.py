"""The fetch screen speaks the user's terms: 작업 ID, all photos by default,
or one photo-number range -- no sessionId / fromNum / toNum."""
import pytest
from PyQt5.QtWidgets import QAbstractButton, QApplication, QLabel, QMessageBox

from labeling_tool.core import i18n
from labeling_tool.ui import fetch_dialog as fd

_app = QApplication.instance() or QApplication([])

SESSIONS = [
    {"sessionId": 49, "inspectionName": "교량 정기점검", "photoCount": 44},
    {"sessionId": 50, "inspectionName": None, "photoCount": 7},
]


@pytest.fixture
def dlg(monkeypatch, tmp_path):
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    i18n.set_language("ko")
    d = fd.FetchDialog(base="https://x", key="k")
    d.client.list_sessions = lambda: SESSIONS
    d._load_sessions()
    yield d
    d.close()


def _texts(d):
    return ([d.windowTitle()]
            + [w.text() for w in d.findChildren(QLabel)]
            + [w.text() for w in d.findChildren(QAbstractButton)])


def test_all_photos_is_the_default(dlg):
    assert dlg.rb_all.isChecked()
    assert not dlg.sp_from.isEnabled() and not dlg.sp_to.isEnabled()
    assert dlg._requested_range() == (0, 0)          # 0 / 0 = everything


def test_a_range_uses_the_two_photo_numbers(dlg):
    dlg.rb_range.setChecked(True)
    assert dlg.sp_from.isEnabled() and dlg.sp_to.isEnabled()
    assert (dlg.sp_from.value(), dlg.sp_to.value()) == (1, 44)   # the whole job
    dlg.sp_from.setValue(10)
    dlg.sp_to.setValue(20)
    assert dlg._requested_range() == (10, 20)


def test_the_range_follows_the_selected_job(dlg):
    dlg.rb_range.setChecked(True)
    dlg.cb_session.setCurrentIndex(1)                              # job 50, 7 photos
    assert (dlg.sp_from.value(), dlg.sp_to.value()) == (1, 7)
    assert dlg.sp_from.minimum() == 1
    # not capped at the count: photo numbers can have gaps (a deleted photo)
    assert dlg.sp_to.maximum() > 7


def test_a_reversed_range_is_refused_before_fetching(dlg, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(dlg, "_fetch_all_photos",
                        lambda *a, **k: pytest.fail("fetched a reversed range"))
    monkeypatch.setattr(fd.Workspace, "default",
                        classmethod(lambda cls, session_id: pytest.fail("touched the disk")))
    dlg.rb_range.setChecked(True)
    dlg.sp_from.setValue(30)
    dlg.sp_to.setValue(10)
    dlg._on_fetch()
    assert shown == [i18n.tr("fetch_range_reversed_msg")]


def test_unknown_photo_count_defaults_the_range_to_the_end(monkeypatch, tmp_path):
    # Typing a job ID by hand (job list unavailable) and pressing Enter
    # reset the range to 1 ~ 1 and fetched a single photo without a word.
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    i18n.set_language("ko")
    d = fd.FetchDialog(base="https://x", key="k")

    def down():
        raise OSError("offline")

    d.client.list_sessions = down
    d._load_sessions()
    fetched = []
    monkeypatch.setattr(d, "_on_fetch", lambda: fetched.append(d._requested_range()))
    try:
        d.rb_range.setChecked(True)
        d.sp_from.setValue(5)
        d.show()
        d.cb_session.setFocus()
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        QTest.keyClicks(d.cb_session.lineEdit(), "49")
        QTest.keyClick(d.cb_session.lineEdit(), Qt.Key_Return)
        assert d.cb_session.count() == 0                 # Enter did not add an item
        assert d._requested_range() == (5, 0)            # 5 ~ end
        assert d.sp_to.text() == i18n.tr("fetch_range_end")
    finally:
        d.close()


def test_reversed_range_message_has_its_own_title(dlg, monkeypatch):
    titles = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: titles.append(a[1]))
    dlg.rb_range.setChecked(True)
    dlg.sp_from.setValue(30)
    dlg.sp_to.setValue(10)
    dlg._on_fetch()
    assert titles == [i18n.tr("fetch_range_title")]


@pytest.mark.parametrize("lang", ["ko", "zh", "en"])
def test_no_developer_names_on_screen(monkeypatch, tmp_path, lang):
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    i18n.set_language(lang)
    d = fd.FetchDialog(base="https://x", key="k")
    d.client.list_sessions = lambda: SESSIONS
    d._load_sessions()
    try:
        texts = " ".join(_texts(d))
        for name in ("sessionId", "fromNum", "toNum"):
            assert name not in texts
        assert d.windowTitle() == i18n.tr("login_new_job")       # same name as the button
        assert i18n.tr("fetch_job_label") in texts
    finally:
        d.close()


def test_korean_names_match_the_glossary(dlg):
    assert i18n.tr("fetch_job_label") == "작업 ID"
    assert dlg.btn_back.text() == "작업 목록"
    assert dlg.btn_fetch.text() == "가져오기"
    assert "sessionId" not in i18n.tr("fetch_input_required_msg")
    assert "작업 ID" in i18n.tr("fetch_input_required_msg")


def test_manual_entry_when_the_job_list_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    i18n.set_language("ko")
    d = fd.FetchDialog(base="https://x", key="k")

    def down():
        raise OSError("offline")

    d.client.list_sessions = down
    d._load_sessions()
    try:
        assert d.cb_session.isEditable()
        assert d.cb_session.lineEdit().placeholderText() == i18n.tr("fetch_job_placeholder")
        d.cb_session.setEditText("49")
        assert d._selected_sid() == 49
    finally:
        d.close()


def test_disabled_range_and_checked_radio_look_the_part(dlg):
    # With the app's dark stylesheet, a disabled range looked editable and
    # the radio indicators were hard to read. Sample backgrounds, not text,
    # so the test does not depend on fonts.
    from labeling_tool.core.window.styles import STYLESHEET
    dlg.setStyleSheet(STYLESHEET)
    dlg.resize(520, 300)
    dlg.show()
    QApplication.processEvents()

    def background(widget):
        img = widget.grab().toImage()
        return img.pixelColor(img.width() // 2, 3).name()       # inside the border

    disabled = background(dlg.sp_from)
    dlg.rb_range.setChecked(True)
    QApplication.processEvents()
    assert background(dlg.sp_from) != disabled

    img = dlg.rb_range.grab().toImage()
    blue = [img.pixelColor(x, y) for x in range(min(24, img.width())) for y in range(img.height())]
    assert any(c.blue() > 180 and c.red() < 90 for c in blue)       # the checked dot ring


def test_a_typed_job_with_an_open_range_downloads_from_there_to_the_last(monkeypatch, tmp_path):
    # The whole path: job list down, typed ID, range 5 ~ 끝, Enter. Photo
    # numbers have gaps and go past the photo count.
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from labeling_tool.session import workspace as ws_mod
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(ws_mod, "DEFAULT_DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(fd, "save_config", lambda *a: None)
    monkeypatch.setattr(fd, "attach_session_log", lambda *a: None)
    photos = [{"timestamp": 1000 + n, "photoId": n, "reportPhotoNum": n, "pxPerCm": 1.0}
              for n in (1, 2, 3, 4, 5, 6, 8, 9, 12)]
    monkeypatch.setattr(fd.FetchDialog, "_fetch_all_photos", staticmethod(lambda c, sid: photos))
    downloaded = []
    monkeypatch.setattr(fd, "download_photos",
                        lambda chosen, *a, **k: downloaded.extend(p["reportPhotoNum"] for p in chosen) or [])
    i18n.set_language("ko")
    d = fd.FetchDialog(base="https://x", key="k")

    def down():
        raise OSError("offline")

    d.client.list_sessions = down
    d._load_sessions()
    try:
        d.rb_range.setChecked(True)
        d.sp_from.setValue(5)
        d.show()
        QTest.keyClicks(d.cb_session.lineEdit(), "49")
        QTest.keyClick(d.cb_session.lineEdit(), Qt.Key_Return)
        assert downloaded == [5, 6, 8, 9, 12]
        assert d.manifest is not None and d.manifest.session_id == 49
    finally:
        d.close()


def _fetch_with(monkeypatch, tmp_path, *, use_range, from_num=5, to_num=7):
    from labeling_tool.session import workspace as ws_mod
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(ws_mod, "DEFAULT_DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(fd, "save_config", lambda *a: None)
    monkeypatch.setattr(fd, "attach_session_log", lambda *a: None)
    photos = [{"timestamp": 1000 + n, "photoId": n, "reportPhotoNum": n, "pxPerCm": 1.0}
              for n in range(1, 11)]
    monkeypatch.setattr(fd.FetchDialog, "_fetch_all_photos", staticmethod(lambda c, sid: photos))
    monkeypatch.setattr(fd, "download_photos", lambda *a, **k: [])
    i18n.set_language("ko")
    d = fd.FetchDialog(base="https://x", key="k")
    d.client.list_sessions = lambda: SESSIONS
    d._load_sessions()
    if use_range:
        d.rb_range.setChecked(True)
        d.sp_from.setValue(from_num)
        d.sp_to.setValue(to_num)
    d._on_fetch()
    return d


def test_a_range_fetch_tells_the_window_which_photos_it_brought(monkeypatch, tmp_path):
    from labeling_tool.session import naming
    d = _fetch_with(monkeypatch, tmp_path, use_range=True)
    try:
        f = d.focus
        assert (f.from_num, f.to_num) == (5, 7)
        assert list(f.filenames) == [naming.stitched_filename(1000 + n) for n in (5, 6, 7)]
    finally:
        d.close()


def test_fetching_all_photos_has_no_focus(monkeypatch, tmp_path):
    d = _fetch_with(monkeypatch, tmp_path, use_range=False)
    try:
        assert d.focus is None and d.manifest is not None
    finally:
        d.close()
