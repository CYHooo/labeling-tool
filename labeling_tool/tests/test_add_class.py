import pytest
import requests
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from labeling_tool.api.errors import ViewerApiError
from labeling_tool.core import classes as C
from labeling_tool.core import i18n
from labeling_tool.tests.test_side_panel import BRUSH, _make_window

_app = QApplication.instance() or QApplication([])


class _Client:
    base_url = "https://viewer.example.com"

    def __init__(self, added=None, error=None):
        self.added, self.error, self.calls = added, error, []

    def add_class(self, name, color):
        self.calls.append((name, color))
        if self.error:
            raise self.error
        return self.added

    def list_classes(self):
        return C.ClassRegistry().to_payload()


def _online(win, client):
    win._client = client
    win._apply_class_registry(C.ClassRegistry(), "ok")


def test_dialog_needs_a_name():
    from labeling_tool.ui.add_class_dialog import AddClassDialog
    d = AddClassDialog("#3C8CFF", i18n.tr)
    ok = d.buttons.button(QDialogButtonBox.Ok)
    assert not ok.isEnabled()
    d.name_edit.setText("  백태 ")
    assert ok.isEnabled() and d.name() == "백태" and d.color() == "#3C8CFF"
    d.name_edit.setText("   ")
    assert not ok.isEnabled()


def test_adding_a_class_selects_it(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        client = _Client(added={"classId": 3, "name": "백태", "kind": "area",
                                "color": "#3C8CFF", "builtin": False})
        _online(win, client)
        monkeypatch.setattr(win, "_ask_new_class", lambda: ("백태", "#3C8CFF"))
        win._on_add_class()
        assert client.calls == [("백태", "#3C8CFF")]
        assert win.class_registry.ids() == [1, 2, 3]
        assert win.canvas.current_class_id == 3
        assert win._class_picker_brush.current_class() == 3
    finally:
        win.close()


def test_adding_an_existing_name_selects_the_existing_class(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        client = _Client(added={"classId": 2, "name": "spalling", "kind": "area",
                                "color": "#3CE63C", "builtin": True})
        _online(win, client)
        monkeypatch.setattr(win, "_ask_new_class", lambda: ("Spalling", "#3C8CFF"))
        win._on_add_class()
        assert win.class_registry.ids() == [1, 2]
        assert win.canvas.current_class_id == 2
    finally:
        win.close()


@pytest.mark.parametrize("error", [
    requests.ConnectionError("down"),
    ViewerApiError("CLASS_LIMIT_EXCEEDED", "full", 409),
])
def test_a_failed_add_shows_why_and_changes_nothing(tmp_path, monkeypatch, error):
    win = _make_window(tmp_path, monkeypatch)
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    try:
        _online(win, _Client(error=error))
        monkeypatch.setattr(win, "_ask_new_class", lambda: ("백태", "#3C8CFF"))
        win._on_add_class()
        assert win.class_registry.ids() == [1, 2] and shown
    finally:
        win.close()


def test_cancel_does_nothing(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        client = _Client()
        _online(win, client)
        monkeypatch.setattr(win, "_ask_new_class", lambda: None)
        win._on_add_class()
        assert client.calls == []
    finally:
        win.close()


def test_add_button_state_follows_the_server(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._tool_picker.setCurrentIndex(BRUSH)
        btn = win._class_picker_brush.add_button
        win._client = _Client()
        win._apply_class_registry(C.ClassRegistry(), "unsupported")
        assert not btn.isEnabled() and btn.toolTip() == i18n.tr("class_add_unsupported")
        win._apply_class_registry(C.ClassRegistry(), "ok")
        assert btn.isEnabled()
    finally:
        win.close()


def test_late_sync_result_keeps_a_class_added_meanwhile(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        client = _Client(added={"classId": 3, "name": "백태", "kind": "area",
                                "color": "#3C8CFF", "builtin": False})
        _online(win, client)
        monkeypatch.setattr(win, "_ask_new_class", lambda: ("백태", "#3C8CFF"))
        win._on_add_class()
        assert win.class_registry.ids() == [1, 2, 3]
        win._on_class_sync_done(C.ClassRegistry(), "ok")
        assert win.class_registry.ids() == [1, 2, 3]
    finally:
        win.close()


def _cached_class_3():
    return C.ClassRegistry().with_class(C.LabelClass(
        3, "백태", "area", "#3C8CFF", False))


def test_server_without_class_api_means_builtins_only(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._tool_picker.setCurrentIndex(BRUSH)
        win._client = _Client()
        # The cache (from an earlier server) knew class 3.
        win._apply_class_registry(_cached_class_3(), "offline")
        win._on_class_sync_done(C.ClassRegistry(), "unsupported")
        assert win.class_registry.ids() == [1, 2]
        assert not win._class_picker_brush.add_button.isEnabled()
    finally:
        win.close()


def test_ok_sync_drops_a_cached_class_the_server_no_longer_lists(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._apply_class_registry(_cached_class_3(), "offline")
        win._on_class_sync_done(C.ClassRegistry(), "ok")
        assert win.class_registry.ids() == [1, 2]
    finally:
        win.close()


def test_offline_sync_keeps_the_cache_and_classes_added_this_session(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        client = _Client(added={"classId": 4, "name": "누수", "kind": "area",
                                "color": "#AA00AA", "builtin": False})
        _online(win, client)
        monkeypatch.setattr(win, "_ask_new_class", lambda: ("누수", "#AA00AA"))
        win._on_add_class()
        win._on_class_sync_done(_cached_class_3(), "offline")
        assert win.class_registry.ids() == [1, 2, 3, 4]
    finally:
        win.close()
