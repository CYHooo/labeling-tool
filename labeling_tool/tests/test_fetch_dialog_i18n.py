"""FetchDialog's session-dropdown labels must come from tr(), not hardcoded
English, so they follow the active language (fix round 1: a Korean user was
seeing "session 123 · 점검명" regardless of the selected language)."""
from PyQt5.QtWidgets import QApplication

from labeling_tool.core import i18n
from labeling_tool.ui.fetch_dialog import FetchDialog

_app = QApplication.instance() or QApplication([])


def _sessions_fixture():
    return [
        {"sessionId": 1, "inspectionName": None, "photoCount": None},
        {"sessionId": 2, "inspectionName": "Bridge A", "photoCount": 5},
    ]


def _labels(monkeypatch, tmp_path, lang):
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language(lang)
    dlg = FetchDialog(base="https://x", key="k")
    dlg.client.list_sessions = _sessions_fixture
    dlg._load_sessions()
    return [dlg.cb_session.itemText(i) for i in range(dlg.cb_session.count())]


def test_session_item_labels_follow_language(monkeypatch, tmp_path):
    en_labels = _labels(monkeypatch, tmp_path, "en")
    assert en_labels[0] == i18n.tr("fetch_session_item", sid=1)
    assert en_labels[1] == (
        i18n.tr("fetch_session_item_named", sid=2, name="Bridge A") + "  " +
        i18n.tr("fetch_photo_count", count=5))

    zh_labels = _labels(monkeypatch, tmp_path, "zh")
    assert zh_labels[0] == i18n.tr("fetch_session_item", sid=1)
    assert zh_labels[1] == (
        i18n.tr("fetch_session_item_named", sid=2, name="Bridge A") + "  " +
        i18n.tr("fetch_photo_count", count=5))

    assert en_labels != zh_labels
