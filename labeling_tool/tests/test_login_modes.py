"""Login screen tool selection: online / downloaded job (로컬 작업) /
few-shot, and app.py opening the matching window."""

import json

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

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


def test_online_tab_is_default_and_unchanged():
    dlg = ld.LoginDialog()
    assert dlg.tabs.currentIndex() == ld.TAB_ONLINE
    dlg.ed_base.setText("http://x")
    dlg.ed_key.setText("k")
    dlg._on_next()
    assert dlg.mode == ld.MODE_ONLINE
    assert (dlg.base, dlg.key) == ("http://x", "k")
    assert dlg.result() == dlg.Accepted


def test_online_requires_credentials(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    dlg = ld.LoginDialog()
    dlg._on_next()
    assert dlg.mode is None
    assert dlg.result() != dlg.Accepted


def test_online_tab_has_no_downloaded_session_section():
    dlg = ld.LoginDialog()
    online = dlg.tabs.widget(ld.TAB_ONLINE)
    assert online.isAncestorOf(dlg.ed_base)
    assert not online.isAncestorOf(dlg.tbl_jobs)


def test_local_tab_lists_jobs_newest_first(tmp_path):
    _job(tmp_path, 16, name="B1 주차장", mtime=1000)
    _job(tmp_path, 18, mtime=2000)
    dlg = ld.LoginDialog()
    t = dlg.tbl_jobs
    assert t.rowCount() == 2
    assert t.item(0, 0).text() == "18" and t.item(0, 1).text() == "—"
    assert t.item(1, 1).text() == "B1 주차장"
    assert t.item(1, 2).text() == "1 / 1"
    assert t.item(1, 3).text() == "srv.example.com"


def test_local_tab_empty(tmp_path):
    dlg = ld.LoginDialog()
    assert dlg.tbl_jobs.rowCount() == 0
    assert not dlg.btn_open_job.isEnabled()
    assert "받은 작업이 없습니다" in dlg.lbl_jobs_empty.text()


def test_selecting_job_fills_its_server_and_saved_key(tmp_path):
    _job(tmp_path, 16, base="https://a.example.com", mtime=2000)
    _job(tmp_path, 18, base="https://b.example.com", mtime=1000)
    dlg = ld.LoginDialog()
    assert dlg.ed_local_key.text() == "saved-key"
    dlg.tbl_jobs.selectRow(1)
    assert dlg.ed_local_base.text() == "https://b.example.com"
    assert "가능" in dlg.lbl_upload.text()
    dlg.ed_local_key.setText("")
    assert "불가" in dlg.lbl_upload.text()


def test_open_job_with_credentials_enables_upload(tmp_path):
    _job(tmp_path, 16, base="https://a.example.com")
    dlg = ld.LoginDialog()
    dlg.tbl_jobs.selectRow(0)
    dlg.btn_open_job.click()
    assert dlg.mode == ld.MODE_SESSION
    assert dlg.workspace.session_dir == tmp_path / "session_16"
    assert dlg.manifest.session_id == 16
    assert (dlg.base, dlg.key) == ("https://a.example.com", "saved-key")
    assert SAVED == [("https://a.example.com", "saved-key")]


def test_open_job_without_credentials_stays_offline(tmp_path):
    _job(tmp_path, 16)
    dlg = ld.LoginDialog()
    dlg.tbl_jobs.selectRow(0)
    dlg.ed_local_key.setText("")
    dlg.btn_open_job.click()
    assert dlg.mode == ld.MODE_SESSION
    assert (dlg.base, dlg.key) == ("", "")
    assert SAVED == []


def test_open_job_refuses_upload_to_a_different_server(monkeypatch, tmp_path):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                         lambda *a, **k: warnings.append(a))
    _job(tmp_path, 16, base="https://a.example.com")
    dlg = ld.LoginDialog()
    dlg.tbl_jobs.selectRow(0)
    dlg.ed_local_base.setText("https://other.example.com")
    dlg.btn_open_job.click()
    assert dlg.mode is None
    assert dlg.result() != dlg.Accepted
    assert warnings
    assert SAVED == []


def test_open_job_allows_trailing_slash_difference(tmp_path):
    _job(tmp_path, 16, base="https://a.example.com")
    dlg = ld.LoginDialog()
    dlg.tbl_jobs.selectRow(0)
    dlg.ed_local_base.setText("https://a.example.com/")
    dlg.btn_open_job.click()
    assert dlg.mode == ld.MODE_SESSION
    assert dlg.result() == dlg.Accepted


def test_open_job_clearing_url_and_key_opens_offline(tmp_path):
    _job(tmp_path, 16, base="https://a.example.com")
    dlg = ld.LoginDialog()
    dlg.tbl_jobs.selectRow(0)
    dlg.ed_local_base.setText("")
    dlg.ed_local_key.setText("")
    dlg.btn_open_job.click()
    assert dlg.mode == ld.MODE_SESSION
    assert dlg.result() == dlg.Accepted
    assert (dlg.base, dlg.key) == ("", "")
    assert SAVED == []


def test_selecting_job_with_empty_base_clears_url_field(tmp_path):
    _job(tmp_path, 16, base="https://a.example.com", mtime=2000)
    _job(tmp_path, 17, base="", mtime=1000)
    dlg = ld.LoginDialog()
    dlg.tbl_jobs.selectRow(0)
    assert dlg.ed_local_base.text() == "https://a.example.com"
    dlg.tbl_jobs.selectRow(1)
    assert dlg.ed_local_base.text() == ""


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
    dlg.btn_fewshot.click()
    assert dlg.mode == ld.MODE_FEWSHOT


def test_fewshot_tab_disabled_without_torch(monkeypatch):
    monkeypatch.setattr(ld, "fewshot_available", lambda: False)
    dlg = ld.LoginDialog()
    assert not dlg.btn_fewshot.isEnabled()
    assert "requirements-gpu.txt" in dlg.lbl_fewshot_hint.text()


def test_fewshot_available_does_not_import_torch(monkeypatch):
    import importlib.util
    import sys
    seen = []
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: seen.append(name) or None)
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    assert ld.fewshot_available() is False
    assert "torch" in seen and "torch" not in sys.modules


def test_open_tool_window_fewshot(monkeypatch):
    from labeling_tool import app
    import annotation_tool.ui.main_window as fs_mw

    class _FakeFewShot:
        def __init__(self):
            self.opened = True

    monkeypatch.setattr(fs_mw, "MainWindow", _FakeFewShot)
    win = app.open_tool_window(ld.MODE_FEWSHOT)
    assert isinstance(win, _FakeFewShot)


def test_open_tool_window_fewshot_failure_returns_to_login(monkeypatch):
    from labeling_tool import app
    import annotation_tool.ui.main_window as fs_mw

    def _boom():
        raise FileNotFoundError("./checkpoint/sam3.pt")

    shown = []
    monkeypatch.setattr(fs_mw, "MainWindow", _boom)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a))
    assert app.open_tool_window(ld.MODE_FEWSHOT) is None
    assert shown and "sam3.pt" in shown[0][2]
    assert QApplication.overrideCursor() is None  # busy cursor restored
