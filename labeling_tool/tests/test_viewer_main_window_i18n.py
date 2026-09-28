"""ViewerMainWindow (labeling_tool/ui/main_window.py, the production upload
screen app.py opens after login) follows the shared language setting."""
from PyQt5.QtWidgets import QApplication, QMessageBox

from labeling_tool.core import i18n
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest
from labeling_tool.ui.main_window import ViewerMainWindow

_app = QApplication.instance() or QApplication([])


def _make_window(tmp_path, monkeypatch):
    # origin/detected folders don't exist in this test; suppress the modal
    # warnings _load_data() would otherwise pop up for that (unrelated here).
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    ws = Workspace(root=tmp_path, session_id=1)
    manifest = Manifest(session_id=1, base="")
    return ViewerMainWindow(ws, manifest, None)


def test_upload_button_follows_language(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    i18n.set_language("ko")
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert win.btn_upload.text() == i18n.tr("vmw_btn_upload")
        i18n.set_language("en")
        assert win.btn_upload.text() == i18n.tr("vmw_btn_upload")
        i18n.set_language("zh")
        assert win.btn_upload.text() == i18n.tr("vmw_btn_upload")
    finally:
        win.close()
