"""Login screen tool selection: online / downloaded job (로컬 작업) /
few-shot, and app.py opening the matching window."""

import json

import pytest
from PyQt5.QtWidgets import QApplication, QLabel, QMessageBox

from labeling_tool.ui import login_dialog as ld

_app = QApplication.instance() or QApplication([])


SAVED = []


@pytest.fixture(autouse=True)
def _no_real_config(monkeypatch, tmp_path):
    # never touch the user's labeling_tool/config.json (holds the API key) or
    # the real downloaded jobs under labeling_tool/data/
    SAVED.clear()
    monkeypatch.setattr(ld, "load_config", lambda: {"apiKey": "saved-key"})
    monkeypatch.setattr(ld, "save_config", lambda base, key: SAVED.append((base, key)))
    monkeypatch.setattr(ld, "DEFAULT_DATA_ROOT", tmp_path)


@pytest.fixture(autouse=True)
def _close_dialogs(monkeypatch):
    """Every test here builds ld.LoginDialog() instances that connect to the
    process-wide LanguageManager singleton and disconnect only on close()
    (see LoginDialog.closeEvent). Track every instance this test creates and
    close() it afterwards, so a test that doesn't call close() itself (most
    of them don't -- they only assert on the dialog) doesn't leave that
    singleton with live listeners for the rest of the suite."""
    created = []
    orig_init = ld.LoginDialog.__init__

    def _tracked_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(ld.LoginDialog, "__init__", _tracked_init)
    yield
    for dlg in created:
        dlg.close()


def _job(root, sid, base="https://srv.example.com", name=None, mtime=1000):
    import os
    d = root / f"session_{sid}"
    d.mkdir()
    mf = d / "manifest.json"
    mf.write_text(json.dumps({
        "sessionId": sid, "base": base, "fetchedAt": None, "inspectionName": name,
        "photos": {"a.jpg": {"filename": "a.jpg", "timestamp": 1, "photo_id": 1,
                             "report_photo_num": 1, "px_per_cm": 1.0, "synced": True}}}))
    os.utime(mf, (mtime, mtime))


def test_labeling_and_fewshot_are_the_only_tabs():
    dlg = ld.LoginDialog()
    assert dlg.tabs.count() == 2
    assert dlg.tabs.currentIndex() == ld.TAB_LABELING
    page = dlg.tabs.widget(ld.TAB_LABELING)
    for w in (dlg.tbl_jobs, dlg.btn_new_job, dlg.btn_open_job, dlg.btn_log_out):
        assert page.isAncestorOf(w)
    # the server is entered once, on the sign-in page (test_sign_in.py)
    for w in (dlg.ed_base, dlg.ed_key):
        assert not page.isAncestorOf(w)


def test_one_server_and_key_field_prefilled_from_config():
    dlg = ld.LoginDialog()
    assert dlg.ed_key.text() == "saved-key"
    assert not hasattr(dlg, "ed_local_base") and not hasattr(dlg, "ed_local_key")


def test_new_job_goes_to_fetch_with_the_entered_server():
    dlg = ld.LoginDialog()
    dlg.ed_base.setText("http://x")
    dlg.ed_key.setText("k")
    dlg.btn_new_job.click()
    assert dlg.mode == ld.MODE_ONLINE
    assert (dlg.base, dlg.key) == ("http://x", "k")
    assert SAVED == [("http://x", "k")]
    assert dlg.result() == dlg.Accepted


def test_new_job_requires_server_and_key(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    dlg = ld.LoginDialog()
    dlg.btn_new_job.click()
    assert dlg.mode is None
    assert dlg.result() != dlg.Accepted


def test_jobs_listed_newest_first(tmp_path):
    _job(tmp_path, 16, name="B1 주차장", mtime=1000)
    _job(tmp_path, 18, mtime=2000)
    dlg = ld.LoginDialog()
    t = dlg.tbl_jobs
    assert t.rowCount() == 2
    assert t.item(0, 0).text() == "18" and t.item(0, 1).text() == "—"
    assert t.item(1, 1).text() == "B1 주차장"
    assert t.item(1, 2).text() == "1 / 1"
    assert t.item(1, 3).text() == "srv.example.com"


def test_no_jobs_points_at_the_new_job_button(tmp_path):
    dlg = ld.LoginDialog()
    assert dlg.tbl_jobs.rowCount() == 0
    assert not dlg.btn_open_job.isEnabled()
    assert dlg.btn_new_job.text() in dlg.lbl_jobs_empty.text()


def test_enter_in_the_fields_neither_opens_nor_fetches(tmp_path):
    """Enter after typing a new server must not open the newest old job (or
    start a fetch): both actions take an explicit click."""
    _job(tmp_path, 16)
    dlg = ld.LoginDialog()
    for btn in (dlg.btn_open_job, dlg.btn_new_job):
        assert not btn.isDefault() and not btn.autoDefault()


def test_selecting_a_job_leaves_the_server_field_alone(tmp_path):
    _job(tmp_path, 16, base="https://a.example.com")
    dlg = ld.LoginDialog()
    dlg.ed_base.setText("https://typed.example.com")
    dlg.tbl_jobs.selectRow(0)
    assert dlg.ed_base.text() == "https://typed.example.com"


def test_upload_state_names_the_job_server_and_needs_a_key(tmp_path):
    _job(tmp_path, 16, base="https://a.example.com")
    dlg = ld.LoginDialog()
    dlg.tbl_jobs.selectRow(0)
    assert "a.example.com" in dlg.lbl_upload.text() and "가능" in dlg.lbl_upload.text()
    dlg.ed_key.setText("")
    assert "불가" in dlg.lbl_upload.text()


def test_open_job_uploads_to_the_server_it_came_from(tmp_path):
    _job(tmp_path, 16, base="https://a.example.com")
    dlg = ld.LoginDialog()
    dlg.ed_base.setText("https://other.example.com")
    dlg.tbl_jobs.selectRow(0)
    dlg.btn_open_job.click()
    assert dlg.mode == ld.MODE_SESSION
    assert dlg.workspace.session_dir == tmp_path / "session_16"
    assert dlg.manifest.session_id == 16
    assert (dlg.base, dlg.key) == ("https://a.example.com", "saved-key")
    assert SAVED == [("https://other.example.com", "saved-key")]


def test_open_job_without_a_key_stays_offline(tmp_path):
    _job(tmp_path, 16)
    dlg = ld.LoginDialog()
    dlg.tbl_jobs.selectRow(0)
    dlg.ed_key.setText("")
    dlg.btn_open_job.click()
    assert dlg.mode == ld.MODE_SESSION
    assert (dlg.base, dlg.key) == ("", "")
    assert SAVED == []


def test_open_job_without_a_recorded_server_uses_the_entered_one(tmp_path):
    _job(tmp_path, 17, base="")
    dlg = ld.LoginDialog()
    dlg.ed_base.setText("https://typed.example.com")
    dlg.tbl_jobs.selectRow(0)
    dlg.btn_open_job.click()
    assert (dlg.base, dlg.key) == ("https://typed.example.com", "saved-key")


def test_open_job_never_saves_an_empty_server(tmp_path):
    _job(tmp_path, 16, base="https://a.example.com")
    dlg = ld.LoginDialog()           # config has a key but no base
    dlg.tbl_jobs.selectRow(0)
    dlg.btn_open_job.click()
    assert dlg.mode == ld.MODE_SESSION
    assert SAVED == []


def test_open_job_with_unloadable_manifest_warns_and_stays_open(monkeypatch, tmp_path):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                         lambda *a, **k: warnings.append(a))
    import os
    d = tmp_path / "session_16"
    d.mkdir()
    mf = d / "manifest.json"
    # listed (readable, has "photos") but not Manifest.load-able: no sessionId
    mf.write_text(json.dumps({"base": "https://a.example.com", "photos": {}}))
    os.utime(mf, (1000, 1000))
    dlg = ld.LoginDialog()
    assert dlg.btn_open_job.isEnabled() or dlg.tbl_jobs.rowCount() >= 0
    dlg.tbl_jobs.selectRow(0)
    dlg.btn_open_job.click()
    assert dlg.mode is None
    assert dlg.result() != dlg.Accepted
    assert warnings


def test_fewshot_tab_enabled_when_torch_installed(monkeypatch):
    monkeypatch.setattr(ld, "fewshot_available", lambda: True)
    dlg = ld.LoginDialog()
    assert dlg.btn_fewshot.isEnabled()
    seen = []
    dlg.fewshotRequested.connect(lambda: seen.append(True))
    dlg.btn_fewshot.click()
    # app.py drives the load and only then accepts; the click itself just
    # asks for it.
    assert seen == [True]


def test_fewshot_tab_disabled_without_torch(monkeypatch):
    monkeypatch.setattr(ld, "fewshot_available", lambda: False)
    dlg = ld.LoginDialog()
    assert not dlg.btn_fewshot.isEnabled()
    assert "requirements-gpu.txt" in dlg.lbl_fewshot_hint.text()


def test_fewshot_tab_source_run_description_mentions_sam3(monkeypatch):
    monkeypatch.setattr(ld, "fewshot_available", lambda: True)
    import labeling_tool.core.app_paths as app_paths
    monkeypatch.setattr(app_paths, "is_frozen", lambda: False)
    dlg = ld.LoginDialog()
    fewshot_page = dlg.tabs.widget(ld.TAB_FEWSHOT)
    text = fewshot_page.findChild(QLabel).text()
    assert "SAM3 / SAM2.1" in text


def test_fewshot_tab_frozen_description_says_sam21_only(monkeypatch):
    monkeypatch.setattr(ld, "fewshot_available", lambda: True)
    import labeling_tool.core.app_paths as app_paths
    monkeypatch.setattr(app_paths, "is_frozen", lambda: True)
    dlg = ld.LoginDialog()
    fewshot_page = dlg.tabs.widget(ld.TAB_FEWSHOT)
    text = fewshot_page.findChild(QLabel).text()
    assert "SAM2.1" in text
    assert "SAM3" not in text


def test_fewshot_tab_frozen_hint_points_to_full_build(monkeypatch):
    monkeypatch.setattr(ld, "fewshot_available", lambda: False)
    import labeling_tool.core.app_paths as app_paths
    monkeypatch.setattr(app_paths, "is_frozen", lambda: True)
    dlg = ld.LoginDialog()
    assert not dlg.btn_fewshot.isEnabled()
    hint = dlg.lbl_fewshot_hint.text()
    assert "lite" in hint
    assert "full" in hint
    assert "pip install" not in hint


def test_fewshot_available_does_not_import_torch(monkeypatch):
    import importlib.util
    import sys
    seen = []
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: seen.append(name) or None)
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    assert ld.fewshot_available() is False
    assert "torch" in seen and "torch" not in sys.modules


def test_load_fewshot_window_builds_it(monkeypatch):
    from labeling_tool import app
    import annotation_tool.ui.main_window as fs_mw

    class _FakeFewShot:
        def __init__(self):
            self.opened = True

    monkeypatch.setattr(fs_mw, "MainWindow", _FakeFewShot)
    win, err = app.load_fewshot_window()
    assert isinstance(win, _FakeFewShot)
    assert err is None


def test_load_fewshot_window_failure_reports_inline(monkeypatch):
    """The failure comes back as text for the login dialog to show; a modal
    QMessageBox here would hang the suite under offscreen Qt."""
    from labeling_tool import app
    import annotation_tool.ui.main_window as fs_mw

    def _boom():
        raise FileNotFoundError("./checkpoint/sam3.pt")

    monkeypatch.setattr(fs_mw, "MainWindow", _boom)
    win, err = app.load_fewshot_window()
    assert win is None
    assert "sam3.pt" in err
    assert QApplication.overrideCursor() is None  # busy cursor restored


def test_login_shows_version_and_check_button(monkeypatch):
    from labeling_tool.update.version import BuildInfo
    monkeypatch.setattr(ld, "read_build_info", lambda: BuildInfo("1.2.3", "full", None))
    dlg = ld.LoginDialog()
    assert "1.2.3" in dlg.lbl_version.text()
    clicked = []
    monkeypatch.setattr(ld, "check_for_updates", lambda parent, force=False: clicked.append(force))
    dlg.btn_check_update.click()
    assert clicked == [True]


def test_check_update_button_reenables_immediately_when_no_thread_started(monkeypatch):
    # e.g. a concurrent check is already running, or it's a dev build: both
    # make check_for_updates return None without starting anything.
    monkeypatch.setattr(ld, "check_for_updates", lambda parent, force=False: None)
    dlg = ld.LoginDialog()
    dlg.btn_check_update.click()
    assert dlg.btn_check_update.isEnabled()


def test_check_update_button_disables_while_running_and_reenables(monkeypatch):
    from PyQt5.QtCore import QThread

    class NoopThread(QThread):
        def run(self):
            pass  # finishes immediately once started

    thread = NoopThread()

    def fake_check(parent, force=False):
        thread.start()
        return thread

    monkeypatch.setattr(ld, "check_for_updates", fake_check)
    dlg = ld.LoginDialog()
    dlg.btn_check_update.click()
    assert not dlg.btn_check_update.isEnabled()
    thread.wait(5000)
    QApplication.instance().processEvents()  # run the queued `finished` callback
    assert dlg.btn_check_update.isEnabled()


def test_language_combo_switches_live(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("ko")
    dlg = ld.LoginDialog()
    assert [dlg.cmb_language.itemData(i) for i in range(dlg.cmb_language.count())] \
        == list(i18n.LANGUAGES)
    ko_title = dlg.tabs.tabText(ld.TAB_LABELING)
    dlg.cmb_language.setCurrentIndex(list(i18n.LANGUAGES).index("en"))
    assert i18n.current_language() == "en"
    assert dlg.tabs.tabText(ld.TAB_LABELING) != ko_title
    assert dlg.btn_new_job.text() == i18n.tr("login_new_job")


def test_dialog_follows_language_changed_signal(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("ko")
    dlg = ld.LoginDialog()
    i18n.set_language("zh")          # changed elsewhere (e.g. the main window)
    assert dlg.btn_new_job.text() == i18n.tr("login_new_job")


def test_job_table_headers_are_translated(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("en")
    dlg = ld.LoginDialog()
    assert dlg.tbl_jobs.horizontalHeaderItem(0).text() == i18n.tr("login_col_job")


def test_closed_dialog_stops_listening_for_language_changes(monkeypatch, tmp_path):
    # app.py's login loop recreates LoginDialog() on every retry, all of them
    # listening on the process-wide LanguageManager singleton; a closed
    # dialog must disconnect so it isn't retranslated (or kept alive) forever.
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("ko")

    dead = ld.LoginDialog()
    dead_calls = []
    monkeypatch.setattr(dead, "retranslate", lambda: dead_calls.append(1))
    dead.close()

    live = ld.LoginDialog()
    live_calls = []
    monkeypatch.setattr(live, "retranslate", lambda: live_calls.append(1))

    i18n.set_language("en")

    assert dead_calls == []
    assert live_calls == [1]
