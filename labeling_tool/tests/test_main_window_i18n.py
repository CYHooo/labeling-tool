"""The main window follows the language chosen on the sign-in / jobs screens
(it has no selector of its own)."""
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.window.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _make_window():
    return MainWindow()


def test_main_window_follows_external_language_change(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language("ko")
    win = _make_window()
    i18n.set_language("zh")                   # e.g. changed on the login screen
    assert win.btn_save.text() == i18n.tr("btn_save")
