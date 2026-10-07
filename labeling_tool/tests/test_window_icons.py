"""The labeling window's and fetch screen's buttons carry icons; arrows move
from the text into the icon so a button never shows two."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

from labeling_tool.core import i18n
from labeling_tool.session.manifest import Manifest
from labeling_tool.session.workspace import Workspace
from labeling_tool.ui.fetch_dialog import FetchDialog
from labeling_tool.ui.main_window import ViewerMainWindow

_app = QApplication.instance() or QApplication([])

WINDOW_BUTTONS = ("_btn_brush_toggle", "_btn_brush_reset",
                  "_btn_brush_save", "_btn_sam_toggle", "_btn_sam_commit", "_btn_sam_cancel", "_btn_sam_undo",
                  "_btn_measure", "_btn_bbox_toggle", "_btn_show_highlight", "_btn_show_repair15",
                  "btn_prev", "btn_next", "btn_save", "btn_upload")


def test_the_labeling_window_buttons_carry_icons(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    win = ViewerMainWindow(Workspace(root=tmp_path, session_id=1), Manifest(session_id=1, base=""), None)
    try:
        for name in WINDOW_BUTTONS:
            assert not getattr(win, name).icon().isNull(), name
        assert win.btn_next.layoutDirection() == Qt.RightToLeft     # chevron on the right
    finally:
        win.close()


def test_the_fetch_buttons_carry_icons():
    dlg = FetchDialog(base="https://x", key="k")
    try:
        assert not dlg.btn_back.icon().isNull() and not dlg.btn_fetch.icon().isNull()
        assert dlg.btn_fetch.objectName() == "primaryAction"
    finally:
        dlg.close()


def test_no_label_keeps_a_text_arrow_its_icon_now_draws():
    for lang in ("ko", "zh", "en"):
        table = getattr(__import__(f"labeling_tool.core.i18n.strings_{lang}", fromlist=["STRINGS"]), "STRINGS")
        for key in ("btn_prev", "btn_next", "fetch_back"):
            assert not any(a in table[key] for a in ("←", "→", "->", "<-")), (lang, key, table[key])
