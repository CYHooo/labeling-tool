"""Login screen tool selection: online / downloaded session / local folder /
few-shot, and app.py opening the matching window."""

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from labeling_tool.ui import login_dialog as ld

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_real_config(monkeypatch):
    # never touch the user's labeling_tool/config.json (holds the API key)
    monkeypatch.setattr(ld, "load_config", lambda: {})
    monkeypatch.setattr(ld, "save_config", lambda base, key: None)
    monkeypatch.setattr(ld, "list_local_session_ids", lambda: [])


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


def test_local_folder_tab_selects_local_mode():
    dlg = ld.LoginDialog()
    dlg.btn_local_folder.click()
    assert dlg.mode == ld.MODE_LOCAL
    assert dlg.result() == dlg.Accepted


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


def test_open_tool_window_local():
    from labeling_tool import app
    from labeling_tool.ui.local_main_window import LocalMainWindow
    win = app.open_tool_window(ld.MODE_LOCAL)
    assert isinstance(win, LocalMainWindow)
    win.close()


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
